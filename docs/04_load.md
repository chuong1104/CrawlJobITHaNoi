# Load Layer - Đẩy dữ liệu vào Data Warehouse

## Tổng quan

Lớp Load nhận **list[JobSchema]** đã validated từ lớp Transform và thực hiện **upsert** vào PostgreSQL. Dùng chiến lược `INSERT ... ON CONFLICT DO UPDATE` để đảm bảo idempotency — chạy lại pipeline không tạo bản ghi duplicate.

---

## Cấu trúc thư mục

```
src/load/
├── __init__.py
├── db_connection.py    ← Quản lý kết nối / connection pool
└── load_to_dw.py       ← Logic upsert batch vào PostgreSQL
```

---

## Database Schema

### Bảng `jobs` (Production)

```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id          VARCHAR(16)     PRIMARY KEY,
    source          VARCHAR(50)     NOT NULL,
    job_url         TEXT            NOT NULL UNIQUE,

    -- Core info
    title           VARCHAR(500)    NOT NULL,
    company         VARCHAR(255)    NOT NULL,
    location        VARCHAR(255),

    -- Salary
    salary_min      BIGINT,
    salary_max      BIGINT,
    salary_currency VARCHAR(3)      DEFAULT 'VND',

    -- Classification
    job_type        VARCHAR(20)     DEFAULT 'FULL_TIME',
    level           VARCHAR(20)     DEFAULT 'MID',
    skills          TEXT[],         -- PostgreSQL array

    -- Content
    description     TEXT            DEFAULT '',
    requirements    TEXT            DEFAULT '',
    benefits        TEXT            DEFAULT '',

    -- Dates
    posted_date     DATE            NOT NULL,
    deadline        DATE,
    scraped_at      TIMESTAMPTZ     NOT NULL,

    -- Audit
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_jobs_source        ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_location      ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_level         ON jobs(level);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type      ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date   ON jobs(posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_min    ON jobs(salary_min);
CREATE INDEX IF NOT EXISTS idx_jobs_skills        ON jobs USING GIN(skills);
```

### Bảng `scrape_logs` (Audit)

```sql
CREATE TABLE IF NOT EXISTS scrape_logs (
    id              SERIAL          PRIMARY KEY,
    run_id          VARCHAR(100)    NOT NULL,   -- Airflow run_id
    source          VARCHAR(50)     NOT NULL,
    started_at      TIMESTAMPTZ     NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20),    -- SUCCESS / FAILED / PARTIAL
    jobs_scraped    INT             DEFAULT 0,
    jobs_inserted   INT             DEFAULT 0,
    jobs_updated    INT             DEFAULT 0,
    jobs_skipped    INT             DEFAULT 0,
    error_message   TEXT
);
```

---

## `db_connection.py`

### Nhiệm vụ

Quản lý kết nối đến PostgreSQL với **connection pooling**, đọc credentials từ biến môi trường.

### Các hàm chính

#### `get_engine() -> Engine`
Tạo SQLAlchemy engine với connection pool. Gọi một lần khi module được load.

```python
# Đọc từ .env:
# POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

engine = create_engine(
    "postgresql+psycopg2://user:pass@host:port/db",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # Kiểm tra kết nối còn sống không trước khi dùng
)
```

#### `get_connection() -> Connection`
Context manager trả về raw psycopg2 connection từ pool:

```python
with get_connection() as conn:
    cur = conn.cursor()
    cur.execute("SELECT 1")
```

#### `init_db()`
Chạy `create_tables.sql` để tạo bảng nếu chưa có. Được gọi trong `airflow-init`.

---

## `load_to_dw.py`

### Nhiệm vụ

Thực hiện **batch upsert** danh sách `JobSchema` vào bảng `jobs`.

### Chiến lược Upsert

```sql
INSERT INTO jobs (
    job_id, source, job_url, title, company, location,
    salary_min, salary_max, salary_currency,
    job_type, level, skills,
    description, requirements, benefits,
    posted_date, deadline, scraped_at, updated_at
)
VALUES %s
ON CONFLICT (job_id) DO UPDATE SET
    title           = EXCLUDED.title,
    company         = EXCLUDED.company,
    location        = EXCLUDED.location,
    salary_min      = EXCLUDED.salary_min,
    salary_max      = EXCLUDED.salary_max,
    salary_currency = EXCLUDED.salary_currency,
    job_type        = EXCLUDED.job_type,
    level           = EXCLUDED.level,
    skills          = EXCLUDED.skills,
    description     = EXCLUDED.description,
    requirements    = EXCLUDED.requirements,
    benefits        = EXCLUDED.benefits,
    deadline        = EXCLUDED.deadline,
    scraped_at      = EXCLUDED.scraped_at,
    updated_at      = NOW()
WHERE
    -- Chỉ update nếu có thay đổi thực sự (tránh UPDATE vô ích)
    jobs.scraped_at < EXCLUDED.scraped_at;
```

**Lý do dùng `ON CONFLICT`:**
- `job_id` = SHA256(source + url) → deterministic, không thay đổi
- Cùng job cào nhiều lần → UPDATE thay vì INSERT duplicate
- Pipeline có thể chạy lại (retry) mà không lo dirty data

### Hàm chính

#### `load_jobs(jobs: list[JobSchema], run_id: str) -> LoadResult`

```python
@dataclass
class LoadResult:
    inserted: int
    updated:  int
    skipped:  int
    errors:   int

def load_jobs(jobs: list[JobSchema], run_id: str, batch_size: int = 500) -> LoadResult:
    """
    Upsert list jobs vào PostgreSQL theo từng batch.
    - batch_size: Số job upsert mỗi lần gọi executemany (default: 500)
    - Ghi kết quả vào bảng scrape_logs
    """
```

**Batch processing:**
```
jobs (1000 records)
  → Batch 1: records [0:500]   → executemany upsert
  → Batch 2: records [500:1000] → executemany upsert
```

Dùng `psycopg2.extras.execute_values()` để bulk insert hiệu quả.

### Xử lý lỗi trong Load

| Tình huống | Xử lý |
|---|---|
| Connection refused | Retry 3 lần với delay 5s, sau đó raise |
| Constraint violation | Log + skip record đó |
| Batch failure | Rollback batch, thử từng record một, log lỗi |
| DeadLock | Retry sau 1s |
| Disk full | Raise ngay, gửi alert |

---

## Luồng Load hoàn chỉnh

```
load_jobs(jobs=[...1000 jobs...], run_id="manual__2026-03-05")
│
├── insert_scrape_log(status="RUNNING")
│
├── Batch 1 (500 jobs)
│   ├── convert jobs → list of tuples
│   ├── execute_values(INSERT ... ON CONFLICT)
│   └── commit
│
├── Batch 2 (500 jobs)
│   ├── convert jobs → list of tuples
│   ├── execute_values(INSERT ... ON CONFLICT)
│   └── commit
│
└── update_scrape_log(
        status="SUCCESS",
        jobs_inserted=X,
        jobs_updated=Y,
        finished_at=NOW()
    )
```

---

## Biến môi trường liên quan

```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=job_scraper_db
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
```

---

## Mở rộng: BigQuery (Optional)

Nếu muốn load lên Google BigQuery thay vì / song song với PostgreSQL:

1. Bỏ comment `google-cloud-bigquery` trong `requirements.txt`
2. Set `GOOGLE_APPLICATION_CREDENTIALS` trong `.env`
3. `load_to_dw.py` sẽ detect biến môi trường và load song song cả PostgreSQL + BigQuery

```python
# Schema BigQuery tương đương:
# Dataset: job_scraper
# Table:   jobs
# Partition by: posted_date (DATE)
# Cluster by:   source, location, level
```
