# Operational Database Design (3NF)

## Overview

Đây là tầng dữ liệu nghiệp vụ chính của hệ thống (Silver Layer ODS - Operational Data Store) chạy trên **PostgreSQL**.

Vai trò:
* Lưu dữ liệu đã làm sạch và chuẩn hóa từ tầng Staging.
* Theo dõi vòng đời tin tuyển dụng (Job Lifecycle).
* Theo dõi lịch sử thay đổi thông tin chi tiết bằng phương pháp Slowing Changing Dimension (SCD) Type 2 (`job_snapshots`).
* Gom nhóm các tin trùng lặp xuyên suốt nhiều nguồn tin tuyển dụng (`job_duplicate_groups`).
* Đóng vai trò là nguồn dữ liệu chuẩn mực ("Single Source of Truth") để đổ sang Data Warehouse.

Schema này được thiết kế theo chuẩn 3NF (Third Normal Form) để tối ưu tính toàn vẹn dữ liệu và loại bỏ dư thừa.

---

# Design Principles

1. **Không lưu dữ liệu trùng lặp**: Loại bỏ tối đa sự dư thừa dữ liệu (ví dụ: tách công ty, địa điểm, kỹ năng thành các bảng riêng).
2. **Mỗi bảng mô tả một thực thể**: Đảm bảo phân tách rõ ràng trách nhiệm của từng bảng.
3. **SCD Type 2 cho dữ liệu động**: Tách thông tin tĩnh định danh (bảng `jobs`) khỏi thông tin biến động theo thời gian (bảng `job_snapshots`).
4. **Theo dõi vòng đời (Lifecycle Tracking)**: Cho phép quản lý và log vết mọi thay đổi trạng thái của tin tuyển dụng thông qua enums và log partitions.
5. **Gom cụm trùng lặp (Entity Resolution)**: Hỗ trợ bí danh công ty (`company_aliases`) và nhóm tin trùng lặp (`job_duplicate_groups`).

---

# Entity Relationship Diagram

```text
               ┌────────────────┐
               │    sources     │
               └───────┬────────┘
                       │ 1
                       │
                       │ N
               ┌───────▼────────┐             ┌─────────────────┐
               │      jobs      │────────────▶│  companies      │
               └───────┬────────┘ N         1 └────────┬────────┘
                       │                               │ 1
                       │ 1                             │
                       │                               │ N
               ┌───────▼────────┐             ┌────────▼────────┐
               │ job_snapshots  │             │ company_aliases │
               └───────┬────────┘             └─────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │ N                         │ N
 ┌───────▼────────┐          ┌───────▼────────┐
 │snapshot_skills │          │snapshot_locs   │
 └───────┬────────┘          └───────┬────────┘
         │ N                         │ N
         │                           │
         │ 1                         │ 1
 ┌───────▼────────┐          ┌───────▼────────┐
 │    skills      │          │   locations    │
 └────────────────┘          └────────────────┘

       ┌───────────────┐            ┌────────────────────────┐
       │  job_events   │            │     crawl_sessions     │
       └───────────────┘            └────────────────────────┘
```

---

# Core Entities & SQL Definitions

Dưới đây là các định nghĩa bảng thực tế trong PostgreSQL Silver Schema (theo [01_create_silver_schema.sql](file:///d:/JobITVN/job_scraper_de_project/scripts/sql/silver/01_create_silver_schema.sql)):

## 1. Enums
Hệ thống sử dụng PostgreSQL Enums để kiểm soát chặt chẽ các trường phân loại:
* `job_status_enum`: `'NEW'`, `'ACTIVE'`, `'UPDATED'`, `'NOT_FOUND'`, `'EXPIRED'`, `'CLOSED'`, `'REPOSTED'`, `'REOPENED'`, `'DUPLICATE'`, `'INVALID'`
* `event_type_enum`: `'JOB_CREATED'`, `'CONTENT_UPDATED'`, `'TITLE_CHANGED'`, `'SALARY_CHANGED'`, `'EXPERIENCE_CHANGED'`, `'LOCATION_CHANGED'`, `'SKILLS_CHANGED'`, `'DEADLINE_CHANGED'`, etc.
* `work_mode_enum`: `'ONSITE'`, `'REMOTE'`, `'HYBRID'`, `'UNKNOWN'`
* `job_level_enum`: `'INTERN'`, `'FRESHER'`, `'JUNIOR'`, `'MIDDLE'`, `'SENIOR'`, `'LEAD'`, `'MANAGER'`, `'C_LEVEL'`, `'UNKNOWN'`
* `job_type_enum`: `'FULL_TIME'`, `'PART_TIME'`, `'CONTRACT'`, `'FREELANCE'`, `'INTERNSHIP'`, `'UNKNOWN'`
* `crawl_status_enum`: `'RUNNING'`, `'SUCCESS'`, `'PARTIAL'`, `'FAILED'`

---

## 2. Bảng Nguồn Tuyển Dụng (`silver.sources`)
Lưu danh mục các website tuyển dụng. Mặc dù bảng seed khởi tạo sẵn 11 nguồn danh mục, hệ thống đang triển khai tự động hóa thu thập dữ liệu với **8 cổng tuyển dụng cốt lõi** (`topcv`, `itviec`, `vietnamworks`, `linkedin`, `careerviet`, `jobsgo`, `joboko`, `123job`).
```sql
CREATE TABLE silver.sources (
    source_id       SMALLSERIAL PRIMARY KEY,
    source_code     VARCHAR(50)  NOT NULL UNIQUE,  -- 'topcv', 'itviec', ...
    display_name    VARCHAR(100) NOT NULL,
    base_url        TEXT         NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## 3. Bảng Công Ty (`silver.companies`)
Lưu thông tin công ty tuyển dụng, hỗ trợ xử lý ẩn danh.
```sql
CREATE TABLE silver.companies (
    company_id      SERIAL       PRIMARY KEY,
    normalized_name TEXT         NOT NULL,  -- Tên đã loại bỏ suffix pháp lý (TNHH, JSC,...)
    display_name    TEXT,                   -- Tên hiển thị đẹp nhất tìm được
    website         TEXT,
    industry        VARCHAR(100),
    company_size    VARCHAR(50),            -- '1-10', '11-50', '51-200', ...
    is_anonymous    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## 4. Bảng Bí Danh Công Ty (`silver.company_aliases`)
Giải quyết vấn đề một công ty có nhiều tên viết khác nhau trên các nguồn tuyển dụng khác nhau. Map nhiều bí danh về một ID công ty chuẩn duy nhất bằng index tìm kiếm mờ trigram.
```sql
CREATE TABLE silver.company_aliases (
    alias_id        SERIAL       PRIMARY KEY,
    company_id      INT          NOT NULL REFERENCES silver.companies(company_id) ON DELETE CASCADE,
    alias_text      TEXT         NOT NULL,  -- Tên gốc từ website nguồn
    source_id       SMALLINT     REFERENCES silver.sources(source_id),
    confidence      SMALLINT     NOT NULL DEFAULT 100 CHECK (confidence BETWEEN 0 AND 100),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (alias_text)
);
```

---

## 5. Bảng Tin Tuyển Dụng Logic (`silver.jobs`)
Lưu trữ thông tin định danh tĩnh bất biến của công việc. KHÔNG lưu nội dung biến động như lương, mô tả, kỹ năng.
```sql
CREATE TABLE silver.jobs (
    job_id              BIGSERIAL       PRIMARY KEY,
    source_id           SMALLINT        NOT NULL REFERENCES silver.sources(source_id),
    company_id          INT             NOT NULL REFERENCES silver.companies(company_id),
    source_job_id       TEXT,           -- ID gốc từ web nguồn
    canonical_url       TEXT,           -- URL đã sạch tham số UTM
    identity_hash       CHAR(16)        NOT NULL,  -- SHA-256[:16] trên các trường bất biến
    latest_content_hash CHAR(16),       -- Hash nội dung phiên bản mới nhất
    job_status          job_status_enum NOT NULL DEFAULT 'NEW',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    not_found_count     SMALLINT        NOT NULL DEFAULT 0 CHECK (not_found_count >= 0),
    inactive_reason     TEXT,
    duplicate_group_id  INT,            -- FK tham chiếu đến duplicate groups
    first_seen_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,
    expired_at          TIMESTAMPTZ,
    reopened_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_jobs_source_job_id UNIQUE (source_id, source_job_id),
    CONSTRAINT uq_jobs_canonical_url UNIQUE (canonical_url)
);
```

---

## 6. Bảng Phiên Bản Tin Tuyển Dụng (`silver.job_snapshots`)
Lưu trữ nội dung động của tin tuyển dụng theo lịch sử hiệu lực (SCD Type 2). Mỗi khi nội dung thay đổi, hệ thống đóng bản ghi hiện tại và thêm một bản ghi snapshot mới.
```sql
CREATE TABLE silver.job_snapshots (
    snapshot_id         BIGSERIAL    PRIMARY KEY,
    job_id              BIGINT       NOT NULL REFERENCES silver.jobs(job_id) ON DELETE CASCADE,
    is_current          BOOLEAN      NOT NULL DEFAULT TRUE,
    valid_from          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,   -- NULL = đang có hiệu lực
    version_number      SMALLINT     NOT NULL DEFAULT 1,
    title_raw           TEXT         NOT NULL,
    title_clean         TEXT,
    description         TEXT,
    requirements        TEXT,
    salary_raw          TEXT,
    salary_min          NUMERIC(15,0), -- VND
    salary_max          NUMERIC(15,0), -- VND
    salary_avg          NUMERIC(15,0) GENERATED ALWAYS AS (
        CASE WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
             THEN (salary_min + salary_max) / 2
             ELSE COALESCE(salary_min, salary_max)
        END
    ) STORED,
    salary_currency     VARCHAR(10)  DEFAULT 'VND',
    salary_is_negotiable BOOLEAN     NOT NULL DEFAULT FALSE,
    experience_raw      TEXT,
    experience_min_years SMALLINT,
    experience_max_years SMALLINT,
    job_level           job_level_enum DEFAULT 'UNKNOWN',
    job_type            job_type_enum  DEFAULT 'UNKNOWN',
    work_mode           work_mode_enum DEFAULT 'UNKNOWN',
    job_family          VARCHAR(100),
    deadline_raw        TEXT,
    deadline_date       DATE,
    is_intern           BOOLEAN      NOT NULL DEFAULT FALSE,
    is_fresher          BOOLEAN      NOT NULL DEFAULT FALSE,
    is_no_experience    BOOLEAN      NOT NULL DEFAULT FALSE,
    is_student_friendly BOOLEAN      NOT NULL DEFAULT FALSE,
    has_conflict_flag   BOOLEAN      NOT NULL DEFAULT FALSE,
    content_hash        CHAR(16)     NOT NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## 7. Bảng Kỹ Năng (`silver.skills`) & Địa Điểm (`silver.locations`)
Bảng danh mục kỹ thuật và địa điểm chuẩn hóa.
```sql
CREATE TABLE silver.skills (
    skill_id        SMALLSERIAL  PRIMARY KEY,
    skill_code      VARCHAR(100) NOT NULL UNIQUE,  -- 'python', 'reactjs'
    display_name    VARCHAR(150) NOT NULL,
    skill_category  VARCHAR(50),                   -- 'language', 'framework'...
    skill_subcategory VARCHAR(50),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE silver.locations (
    location_id     SMALLSERIAL  PRIMARY KEY,
    location_code   VARCHAR(50)  NOT NULL UNIQUE,  -- 'ha_noi', 'ho_chi_minh'
    display_name    VARCHAR(100) NOT NULL,
    region          VARCHAR(50),                    -- 'north', 'south', 'central'
    is_remote       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## 8. Bảng Junction M:N
Do một snapshot có thể yêu cầu nhiều kỹ năng hoặc địa điểm, các bảng trung gian giải quyết mối quan hệ Nhiều-Nhiều:
```sql
CREATE TABLE silver.job_snapshot_skills (
    id              BIGSERIAL    PRIMARY KEY,
    snapshot_id     BIGINT       NOT NULL REFERENCES silver.job_snapshots(snapshot_id) ON DELETE CASCADE,
    skill_id        SMALLINT     NOT NULL REFERENCES silver.skills(skill_id),
    skill_position  SMALLINT     NOT NULL DEFAULT 0,
    is_primary      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, skill_id)
);

CREATE TABLE silver.job_snapshot_locations (
    id              BIGSERIAL    PRIMARY KEY,
    snapshot_id     BIGINT       NOT NULL REFERENCES silver.job_snapshots(snapshot_id) ON DELETE CASCADE,
    location_id     SMALLINT     NOT NULL REFERENCES silver.locations(location_id),
    is_primary      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, location_id)
);
```

---

## 9. Bảng Nhóm Trùng Lặp Cross-Source (`silver.job_duplicate_groups`)
Gom cụm các job giống nhau đăng trên nhiều trang web tuyển dụng (ví dụ: FPT tuyển DE đăng trên cả ITviec lẫn TopCV).
```sql
CREATE TABLE silver.job_duplicate_groups (
    group_id            SERIAL       PRIMARY KEY,
    canonical_job_id    BIGINT       NOT NULL REFERENCES silver.jobs(job_id),  -- Job đại diện chính
    group_name          TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE silver.job_duplicate_group_members (
    id              SERIAL       PRIMARY KEY,
    group_id        INT          NOT NULL REFERENCES silver.job_duplicate_groups(group_id) ON DELETE CASCADE,
    job_id          BIGINT       NOT NULL REFERENCES silver.jobs(job_id) ON DELETE CASCADE,
    similarity_score NUMERIC(5,4) CHECK (similarity_score BETWEEN 0 AND 1),
    match_method    VARCHAR(50),  -- 'identity_hash', 'tfidf_cosine', etc.
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (group_id, job_id)
);
```

---

## 10. Nhật Ký Biến Động Vòng Đời (`silver.job_events`)
Lưu toàn bộ audit trail biến động của tin tuyển dụng. Bảng này được chia **partition theo tháng** để tối ưu hóa hiệu năng truy xuất và dọn dẹp dữ liệu cũ.
```sql
CREATE TABLE silver.job_events (
    event_id        BIGSERIAL,
    job_id          BIGINT          NOT NULL REFERENCES silver.jobs(job_id) ON DELETE CASCADE,
    event_type      event_type_enum NOT NULL,
    source_id       SMALLINT        REFERENCES silver.sources(source_id),
    crawl_session_id BIGINT         REFERENCES silver.crawl_sessions(session_id),
    old_values      JSONB,           -- JSON chứa giá trị cũ
    new_values      JSONB,           -- JSON chứa giá trị mới
    reason          TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, created_at)
) PARTITION BY RANGE (created_at);
```

---

## 11. Metadata Phiên Crawl (`silver.crawl_sessions`)
Quản lý trạng thái và thống kê chất lượng dữ liệu của từng lượt chạy cào dữ liệu. Đóng vai trò làm chốt chặn an toàn (guard) cho logic tự động đóng tin (auto-close).
```sql
CREATE TABLE silver.crawl_sessions (
    session_id      BIGSERIAL    PRIMARY KEY,
    run_date        DATE         NOT NULL,
    source_id       SMALLINT     REFERENCES silver.sources(source_id),
    crawl_status    crawl_status_enum NOT NULL DEFAULT 'RUNNING',
    total_scraped   INT          NOT NULL DEFAULT 0,
    total_validated INT          NOT NULL DEFAULT 0,
    total_rejected  INT          NOT NULL DEFAULT 0,
    rejection_rate  NUMERIC(5,2) GENERATED ALWAYS AS (
        CASE WHEN total_scraped > 0
             THEN ROUND((total_rejected::NUMERIC / total_scraped) * 100, 2)
             ELSE 0
        END
    ) STORED,
    pages_scraped   INT          NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    duration_seconds INT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (completed_at - started_at))::INT
    ) STORED
);
```

---

## 12. Bảng Đệm Staging (`staging.stg_jobs`)
Nơi nhận kết quả biến đổi dữ liệu của `dbt` từ file DuckDB local nạp vào PostgreSQL, làm đầu vào cho Python Silver Sync Engine xử lý CDC.
```sql
CREATE TABLE staging.stg_jobs (
    stg_id              BIGSERIAL    PRIMARY KEY,
    source_code         VARCHAR(50)  NOT NULL,
    source_job_id       TEXT,
    canonical_url       TEXT,
    title_raw           TEXT         NOT NULL,
    company_raw         TEXT         NOT NULL,
    location_raw        TEXT,
    salary_raw          TEXT,
    experience_raw      TEXT,
    skills_raw          TEXT[],
    job_type_raw        VARCHAR(100),
    description         TEXT,
    deadline_raw        TEXT,
    posted_date_raw     DATE,
    title_clean         TEXT,
    company_normalized  TEXT,
    salary_min          NUMERIC(15,0),
    salary_max          NUMERIC(15,0),
    salary_currency     VARCHAR(10),
    salary_is_negotiable BOOLEAN      DEFAULT FALSE,
    experience_min_years SMALLINT,
    experience_max_years SMALLINT,
    job_level           job_level_enum DEFAULT 'UNKNOWN',
    job_type            job_type_enum  DEFAULT 'UNKNOWN',
    work_mode           work_mode_enum DEFAULT 'UNKNOWN',
    location_normalized VARCHAR(50),
    job_family          VARCHAR(100),
    deadline_date       DATE,
    is_intern           BOOLEAN      DEFAULT FALSE,
    is_fresher          BOOLEAN      DEFAULT FALSE,
    identity_hash       CHAR(16)     NOT NULL,
    content_hash        CHAR(16)     NOT NULL,
    change_type         VARCHAR(20),
    scraped_at          TIMESTAMPTZ  NOT NULL,
    processed_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    pipeline_version    VARCHAR(20)  NOT NULL DEFAULT '2.0',
    batch_date          DATE         NOT NULL DEFAULT CURRENT_DATE
);
```

---

# Index Strategy Optimization

Để tăng tốc độ truy vấn nghiệp vụ và quá trình so khớp trùng lặp:
1. **Bí danh Công ty:** GIN index sử dụng `gin_trgm_ops` trên cột `alias_text` giúp fuzzy search cực nhanh bằng thuật toán khoảng cách Trigram.
   ```sql
   CREATE INDEX idx_company_aliases_text_trgm ON silver.company_aliases USING gin (alias_text gin_trgm_ops);
   ```
2. **Tìm kiếm current snapshots:**
   ```sql
   CREATE INDEX idx_snapshots_job_current ON silver.job_snapshots (job_id, is_current);
   ```
3. **Cờ hoạt động:**
   ```sql
   CREATE INDEX idx_jobs_status_active ON silver.jobs (job_status, is_active);
   ```
4. **Các khóa so khớp:** Đánh index trên `identity_hash` và `content_hash` của cả `silver.jobs`, `silver.job_snapshots`, và `staging.stg_jobs`.
