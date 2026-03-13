# 04 — Load Layer — Đẩy Dữ liệu vào Data Warehouse

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Lớp Load được cập nhật để phản ánh schema database mở rộng phục vụ các tính năng NLP và Intelligence (bảng `job_skills`, `skills`, `job_embeddings`, `companies`, `users`, `learning_resources`), đồng thời làm rõ ranh giới trách nhiệm giữa Load ETL và Load NLP.

---

## Tổng quan

Lớp Load nhận `list[JobSchema]` đã validated từ lớp Transform và thực hiện **upsert** vào PostgreSQL. Nguyên tắc cốt lõi là **idempotency** — pipeline có thể chạy lại bất kỳ lúc nào mà không tạo duplicate, không mất dữ liệu.

Lớp Load **chỉ** chịu trách nhiệm đẩy dữ liệu đã có trong JobSchema vào bảng `jobs`. Việc populate các bảng phụ như `job_skills` và `job_embeddings` là nhiệm vụ của NLP DAG riêng biệt, chạy sau ETL DAG.

---

## Cấu trúc Thư mục

```
src/load/
├── __init__.py
├── db_connection.py    ← Quản lý kết nối / connection pool
└── load_to_dw.py       ← Logic upsert batch vào PostgreSQL
```

---

## Database Schema Đầy đủ

### Bảng `jobs` (Core — ETL Layer)

```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id          VARCHAR(16)     PRIMARY KEY,
    source          VARCHAR(50)     NOT NULL,
    job_url         TEXT            NOT NULL UNIQUE,

    title           VARCHAR(500)    NOT NULL,
    company         VARCHAR(255)    NOT NULL,
    location        VARCHAR(255),

    salary_min      BIGINT,
    salary_max      BIGINT,
    salary_currency VARCHAR(3)      DEFAULT 'VND',

    job_type        VARCHAR(20)     DEFAULT 'FULL_TIME',
    level           VARCHAR(20)     DEFAULT 'MID',
    skills          TEXT[],

    description     TEXT            DEFAULT '',
    requirements    TEXT            DEFAULT '',
    benefits        TEXT            DEFAULT '',

    posted_date     DATE            NOT NULL,
    deadline        DATE,
    scraped_at      TIMESTAMPTZ     NOT NULL,

    -- NLP processing status
    nlp_processed   BOOLEAN         DEFAULT FALSE,
    embedding_ready BOOLEAN         DEFAULT FALSE,

    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- Indexes phục vụ ETL và Search
CREATE INDEX IF NOT EXISTS idx_jobs_source        ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_location      ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_level         ON jobs(level);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type      ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date   ON jobs(posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_min    ON jobs(salary_min);
CREATE INDEX IF NOT EXISTS idx_jobs_skills        ON jobs USING GIN(skills);
CREATE INDEX IF NOT EXISTS idx_jobs_nlp_processed ON jobs(nlp_processed) WHERE nlp_processed = FALSE;
```

**Hai trường bổ sung so với schema cũ:**
- `nlp_processed`: NLP DAG sẽ query `WHERE nlp_processed = FALSE` để tìm jobs cần xử lý, sau đó set thành TRUE.
- `embedding_ready`: Tương tự, flag cho biết job đã có embedding vector hay chưa.

### Bảng `scrape_logs` (Audit)

```sql
CREATE TABLE IF NOT EXISTS scrape_logs (
    id              SERIAL          PRIMARY KEY,
    run_id          VARCHAR(100)    NOT NULL,
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

### Bảng `companies` (Company Crawler)

```sql
CREATE TABLE IF NOT EXISTS companies (
    company_id      SERIAL          PRIMARY KEY,
    name            VARCHAR(255)    NOT NULL,
    alias           VARCHAR(255),
    website         TEXT,
    career_url      TEXT,
    industry        VARCHAR(100),
    size            VARCHAR(50),
    address         TEXT,
    source_portal   VARCHAR(50)     DEFAULT 'jobsgo',
    crawl_status    VARCHAR(20)     DEFAULT 'pending',
    -- pending / career_found / career_not_found / crawl_failed
    crawled_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(name, website)
);

CREATE INDEX IF NOT EXISTS idx_companies_crawl_status ON companies(crawl_status);
CREATE INDEX IF NOT EXISTS idx_companies_industry     ON companies(industry);
```

### Bảng `skills` và `job_skills` (NLP Layer — tạo sẵn schema)

```sql
-- Danh mục kỹ năng chuẩn hóa
CREATE TABLE IF NOT EXISTS skills (
    skill_id        SERIAL          PRIMARY KEY,
    name            VARCHAR(100)    NOT NULL UNIQUE,
    category        VARCHAR(50),    -- TECHNICAL / SOFT / CERTIFICATION / TOOL
    aliases         TEXT[],
    parent_skill_id INT             REFERENCES skills(skill_id),
    difficulty_level VARCHAR(20)   -- FUNDAMENTAL / INTERMEDIATE / ADVANCED
);

-- Quan hệ tiên quyết giữa kỹ năng (phục vụ Learning Path)
CREATE TABLE IF NOT EXISTS skill_prerequisites (
    skill_id            INT NOT NULL REFERENCES skills(skill_id),
    prerequisite_id     INT NOT NULL REFERENCES skills(skill_id),
    is_hard_requirement BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (skill_id, prerequisite_id)
);

-- Mapping nhiều-nhiều Job ↔ Skill (do NLP Layer populate)
CREATE TABLE IF NOT EXISTS job_skills (
    job_id          VARCHAR(16)     NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    skill_id        INT             NOT NULL REFERENCES skills(skill_id),
    confidence      FLOAT           CHECK (confidence BETWEEN 0 AND 1),
    position        VARCHAR(10),    -- title / desc / req (vị trí xuất hiện)
    PRIMARY KEY (job_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_job_skills_skill_id ON job_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_confidence ON job_skills(confidence DESC);
```

### Bảng `job_embeddings` (NLP Layer — tạo sẵn schema)

```sql
-- Yêu cầu extension pgvector
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS job_embeddings (
    job_id          VARCHAR(16)     PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
    embedding       VECTOR(768),    -- Dimension phụ thuộc model (PhoBERT: 768)
    model_name      VARCHAR(100)    NOT NULL,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- HNSW index cho Approximate Nearest Neighbor search
CREATE INDEX IF NOT EXISTS idx_job_embeddings_hnsw
    ON job_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### Bảng Users và Learning (Web App Layer — tạo sẵn schema)

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255)    UNIQUE NOT NULL,
    name            VARCHAR(100),
    target_role     VARCHAR(100),
    experience_years SMALLINT,
    location_pref   VARCHAR(100),
    salary_expectation BIGINT,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ     DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_skills (
    user_id         UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    skill_id        INT             NOT NULL REFERENCES skills(skill_id),
    proficiency_level VARCHAR(20),  -- BEGINNER / INTERMEDIATE / ADVANCED
    source          VARCHAR(20),    -- declared / inferred / verified
    PRIMARY KEY (user_id, skill_id)
);

CREATE TABLE IF NOT EXISTS user_interactions (
    interaction_id  BIGSERIAL       PRIMARY KEY,
    user_id         UUID            NOT NULL REFERENCES users(user_id),
    job_id          VARCHAR(16)     NOT NULL REFERENCES jobs(job_id),
    action_type     VARCHAR(10)     NOT NULL, -- view / save / apply / skip
    session_id      VARCHAR(100),
    timestamp       TIMESTAMPTZ     DEFAULT NOW(),
    device_type     VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_interactions_user_id   ON user_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_job_id    ON user_interactions(job_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON user_interactions(timestamp DESC);

CREATE TABLE IF NOT EXISTS learning_resources (
    resource_id     SERIAL          PRIMARY KEY,
    title           VARCHAR(300)    NOT NULL,
    url             TEXT            NOT NULL UNIQUE,
    platform        VARCHAR(50),    -- Coursera / Udemy / YouTube / ...
    resource_type   VARCHAR(30),    -- course / article / book / certification / video
    duration_hours  FLOAT,
    cost            NUMERIC(10,2),  -- 0 = miễn phí
    language        VARCHAR(10)     DEFAULT 'vi',
    rating          FLOAT,
    skills_covered  INT[],          -- mảng skill_id
    last_verified_at DATE,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);
```

---

## `db_connection.py`

### Nhiệm vụ

Quản lý kết nối đến PostgreSQL với connection pooling, đọc credentials từ biến môi trường. Thiết kế singleton — engine chỉ được tạo một lần khi module load.

### Cấu hình Connection Pool

Engine được tạo với các tham số: `pool_size=5` (số kết nối thường trực), `max_overflow=10` (số kết nối bổ sung tạm thời khi cần), `pool_pre_ping=True` (kiểm tra kết nối còn sống trước khi dùng, tránh lỗi "connection closed" sau idle), `pool_recycle=3600` (tái tạo kết nối sau 1 giờ).

### Hàm `init_db()`

Chạy `dags/sql/create_tables.sql` để tạo tất cả bảng nếu chưa có. Được gọi trong `airflow-init` service khi khởi động lần đầu. An toàn để gọi nhiều lần do toàn bộ dùng `CREATE TABLE IF NOT EXISTS` và `CREATE INDEX IF NOT EXISTS`.

---

## `load_to_dw.py`

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
    updated_at      = NOW(),
    -- Reset NLP flags khi nội dung thay đổi
    nlp_processed   = CASE
        WHEN jobs.description != EXCLUDED.description
          OR jobs.requirements != EXCLUDED.requirements
        THEN FALSE
        ELSE jobs.nlp_processed
    END,
    embedding_ready = CASE
        WHEN jobs.description != EXCLUDED.description
          OR jobs.title != EXCLUDED.title
        THEN FALSE
        ELSE jobs.embedding_ready
    END
WHERE
    jobs.scraped_at < EXCLUDED.scraped_at;
```

**Điểm mới so với version cũ:** Khi nội dung job thay đổi (mô tả, tiêu đề bị cập nhật), các flag `nlp_processed` và `embedding_ready` được reset về FALSE để NLP DAG tự động xử lý lại.

### Hàm `load_jobs(jobs, run_id, batch_size=500) -> LoadResult`

Upsert list JobSchema vào PostgreSQL theo từng batch 500 records. Sử dụng `psycopg2.extras.execute_values()` cho bulk insert hiệu quả hơn `executemany` thông thường.

**LoadResult** trả về: `inserted` (số bản ghi mới), `updated` (số bản ghi đã có và được cập nhật), `skipped` (số bản ghi trùng lặp không thay đổi), `errors` (số bản ghi gặp lỗi).

### Hàm `load_companies(companies, run_id) -> LoadResult`

Upsert danh sách công ty từ Company Crawler vào bảng `companies`. Conflict resolution trên `(name, website)`. Không reset các trường `crawl_status` nếu đã được crawler career page xử lý.

### Xử lý Lỗi trong Load

| Tình huống | Xử lý | Severity |
|---|---|---|
| Connection refused | Retry 3 lần × delay 5s → raise | CRITICAL |
| Constraint violation | Log + skip record | WARNING |
| Batch failure | Rollback batch → thử từng record một | ERROR |
| DeadLock | Retry sau 1s | WARNING |
| Disk full | Raise ngay, alert | CRITICAL |
| pgvector không khả dụng | Warning, bỏ qua tạo embedding index | WARNING |

---

## Luồng Load Hoàn chỉnh

```
load_jobs(jobs=[...1000 jobs...], run_id="scheduled__2026-03-11T06:00:00")
│
├── insert_scrape_log(status="RUNNING", source, started_at)
│
├── Batch 1: records [0:500]
│   ├── convert JobSchema list → list of tuples
│   ├── execute_values(INSERT ... ON CONFLICT)
│   └── commit → ghi nhận inserted/updated/skipped
│
├── Batch 2: records [500:1000]
│   ├── convert → tuples
│   ├── execute_values(INSERT ... ON CONFLICT)
│   └── commit
│
└── update_scrape_log(
        status="SUCCESS",
        jobs_inserted=X, jobs_updated=Y, jobs_skipped=Z,
        finished_at=NOW()
    )
```

---

## Mối quan hệ giữa Load ETL và Load NLP

```
ETL DAG (hàng ngày, 6:00 AM):
  extract → transform → load_jobs()
    └─ Đẩy vào bảng `jobs` với nlp_processed=FALSE, embedding_ready=FALSE

NLP DAG (chạy sau ETL DAG hoàn thành, ~7:30 AM):
  query WHERE nlp_processed=FALSE
    └─ skill_extraction → INSERT INTO job_skills
    └─ text_embedding   → INSERT INTO job_embeddings
    └─ UPDATE jobs SET nlp_processed=TRUE, embedding_ready=TRUE
```

Thiết kế này đảm bảo: ngay khi ETL xong, dữ liệu mới đã có trong `jobs` cho các query cơ bản. Tính năng search ngữ nghĩa và recommendation sẽ include jobs mới sau khi NLP DAG hoàn thành (~1.5 giờ sau).

---

## Biến Môi trường

```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=job_scraper_db
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow        # Thay bằng password mạnh ở production
```

---

## Mở rộng: BigQuery (Optional)

Nếu muốn load lên Google BigQuery để phân tích quy mô lớn hoặc tích hợp với Google Data Studio:
- Bật `google-cloud-bigquery` trong `requirements.txt`
- Set `GOOGLE_APPLICATION_CREDENTIALS` trong `.env`
- `load_to_dw.py` detect biến môi trường và load song song cả PostgreSQL + BigQuery
- Schema BigQuery: Dataset `job_scraper`, Table `jobs`, Partition by `posted_date`, Cluster by `source, location, level`
