# Operational Database Design (3NF)

## Overview

Đây là tầng dữ liệu nghiệp vụ chính của hệ thống.

Vai trò:

* Lưu dữ liệu đã chuẩn hóa
* Theo dõi vòng đời việc làm
* Theo dõi lịch sử thay đổi
* Phát hiện duplicate jobs
* Là nguồn dữ liệu cho Data Warehouse

Schema này được thiết kế theo chuẩn 3NF.

---

# Design Principles

## Principle 1

Không lưu dữ liệu lặp.

---

## Principle 2

Mỗi bảng chỉ mô tả một thực thể.

---

## Principle 3

Tách lịch sử thay đổi khỏi dữ liệu hiện tại.

---

## Principle 4

Cho phép tracking lifecycle.

---

## Principle 5

Cho phép deduplication.

---

# Entity Relationship Diagram

```text
sources
    │
    ▼
jobs
    │
    ▼
job_snapshots
    │
    ├─────────────┐
    ▼             ▼
job_snapshot_skills
job_snapshot_locations

companies
    │
    ▼
jobs

skills
    │
    ▼
job_snapshot_skills

locations
    │
    ▼
job_snapshot_locations

job_events

duplicate_groups
```

---

# Core Entities

## sources

Nguồn dữ liệu.

Ví dụ:

* ITviec
* TopCV
* VietnamWorks
* TopDev
* Glints

---

### Table

```sql
CREATE TABLE sources (
    source_id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) UNIQUE,
    source_url TEXT,
    created_at TIMESTAMP
);
```

---

# companies

Thông tin doanh nghiệp.

---

### Problem

Cùng một công ty có thể xuất hiện dưới nhiều tên:

```text
FPT Software

FPT Software JSC

FPT Software Co., Ltd
```

---

### Table

```sql
CREATE TABLE companies (
    company_id BIGSERIAL PRIMARY KEY,

    company_name VARCHAR(255),

    normalized_name VARCHAR(255),

    website TEXT,

    company_size VARCHAR(50),

    industry VARCHAR(255),

    created_at TIMESTAMP,

    updated_at TIMESTAMP
);
```

---

# company_aliases

Lưu các tên khác nhau.

---

```sql
CREATE TABLE company_aliases (
    alias_id BIGSERIAL PRIMARY KEY,

    company_id BIGINT
        REFERENCES companies(company_id),

    alias_name VARCHAR(255)
);
```

---

# jobs

Thực thể Job gốc.

Một record tương ứng một công việc logic.

---

### Ví dụ

Data Engineer Intern

---

Không lưu:

* salary
* skills
* locations

vì các trường này có thể thay đổi.

---

```sql
CREATE TABLE jobs (

    job_id BIGSERIAL PRIMARY KEY,

    company_id BIGINT
        REFERENCES companies(company_id),

    source_id INTEGER
        REFERENCES sources(source_id),

    source_job_id VARCHAR(255),

    canonical_job_key VARCHAR(255),

    first_seen_at TIMESTAMP,

    last_seen_at TIMESTAMP,

    current_status VARCHAR(50),

    created_at TIMESTAMP
);
```

---

# Why Job Table Is Small

Job là thực thể ổn định.

Các trường thay đổi sẽ nằm ở snapshot.

---

# job_snapshots

Đây là bảng quan trọng nhất hệ thống.

Mỗi lần job thay đổi:

* title
* salary
* requirements
* description

=> tạo snapshot mới.

---

```sql
CREATE TABLE job_snapshots (

    snapshot_id BIGSERIAL PRIMARY KEY,

    job_id BIGINT
        REFERENCES jobs(job_id),

    title TEXT,

    description TEXT,

    salary_min NUMERIC,

    salary_max NUMERIC,

    salary_currency VARCHAR(20),

    employment_type VARCHAR(50),

    experience_required VARCHAR(100),

    posted_date DATE,

    expired_date DATE,

    content_hash VARCHAR(128),

    valid_from TIMESTAMP,

    valid_to TIMESTAMP,

    is_current BOOLEAN
);
```

---

# Why Snapshot Table

Ví dụ:

Ngày 01/06

```text
Salary:
8-10 triệu
```

Ngày 10/06

```text
Salary:
10-15 triệu
```

Không overwrite.

Tạo snapshot mới.

---

# skills

Dictionary kỹ năng.

---

```sql
CREATE TABLE skills (

    skill_id BIGSERIAL PRIMARY KEY,

    skill_name VARCHAR(255),

    normalized_skill VARCHAR(255)
);
```

---

# Example

```text
Python

SQL

Airflow

Spark

Docker
```

---

# job_snapshot_skills

Many-to-many.

---

```sql
CREATE TABLE job_snapshot_skills (

    snapshot_id BIGINT
        REFERENCES job_snapshots(snapshot_id),

    skill_id BIGINT
        REFERENCES skills(skill_id),

    PRIMARY KEY (
        snapshot_id,
        skill_id
    )
);
```

---

# locations

Danh mục địa điểm.

---

```sql
CREATE TABLE locations (

    location_id BIGSERIAL PRIMARY KEY,

    city VARCHAR(100),

    district VARCHAR(100),

    province VARCHAR(100)
);
```

---

# job_snapshot_locations

Many-to-many.

---

```sql
CREATE TABLE job_snapshot_locations (

    snapshot_id BIGINT
        REFERENCES job_snapshots(snapshot_id),

    location_id BIGINT
        REFERENCES locations(location_id),

    PRIMARY KEY (
        snapshot_id,
        location_id
    )
);
```

---

# job_families

Nhóm nghề nghiệp chuẩn hóa.

---

Ví dụ:

```text
Data Engineer

Data Analyst

Backend Engineer

Frontend Engineer

QA Engineer

DevOps Engineer
```

---

```sql
CREATE TABLE job_families (

    family_id BIGSERIAL PRIMARY KEY,

    family_name VARCHAR(255)
);
```

---

# job_snapshot_families

```sql
CREATE TABLE job_snapshot_families (

    snapshot_id BIGINT,

    family_id BIGINT,

    PRIMARY KEY (
        snapshot_id,
        family_id
    )
);
```

---

# duplicate_groups

Nhóm các job trùng nhau.

---

Ví dụ:

```text
TopCV
ITviec
VietnamWorks
```

thực chất cùng một job.

---

```sql
CREATE TABLE duplicate_groups (

    duplicate_group_id BIGSERIAL PRIMARY KEY,

    confidence_score NUMERIC
);
```

---

# duplicate_group_members

```sql
CREATE TABLE duplicate_group_members (

    duplicate_group_id BIGINT,

    job_id BIGINT
);
```

---

# job_events

Lưu lịch sử vòng đời.

---

## Example

```text
NEW

ACTIVE

UPDATED

EXPIRED

REPOSTED
```

---

```sql
CREATE TABLE job_events (

    event_id BIGSERIAL PRIMARY KEY,

    job_id BIGINT
        REFERENCES jobs(job_id),

    event_type VARCHAR(50),

    event_timestamp TIMESTAMP,

    metadata JSONB
);
```

---

# Crawl Metadata

## crawl_runs

```sql
CREATE TABLE crawl_runs (

    crawl_run_id BIGSERIAL PRIMARY KEY,

    source_id INTEGER,

    started_at TIMESTAMP,

    finished_at TIMESTAMP,

    status VARCHAR(50)
);
```

---

# crawl_errors

```sql
CREATE TABLE crawl_errors (

    error_id BIGSERIAL PRIMARY KEY,

    crawl_run_id BIGINT,

    url TEXT,

    error_message TEXT,

    occurred_at TIMESTAMP
);
```

---

# Lifecycle Design

## Statuses

```text
NEW

ACTIVE

UPDATED

EXPIRED

CLOSED

NOT_FOUND

REPOSTED
```

---

# Typical Flow

```text
NEW
 ↓

ACTIVE
 ↓

UPDATED
 ↓

EXPIRED
 ↓

CLOSED
```

---

# Index Strategy

## jobs

```sql
CREATE INDEX idx_jobs_status
ON jobs(current_status);
```

---

## snapshots

```sql
CREATE INDEX idx_snapshot_job
ON job_snapshots(job_id);
```

---

```sql
CREATE INDEX idx_snapshot_current
ON job_snapshots(is_current);
```

---

## skills

```sql
CREATE INDEX idx_skill_name
ON skills(normalized_skill);
```

---

## companies

```sql
CREATE INDEX idx_company_normalized
ON companies(normalized_name);
```

---

# Why This Design Works

Hệ thống hỗ trợ:

✓ SCD Type 2

✓ CDC

✓ Incremental Load

✓ Job Lifecycle

✓ Duplicate Detection

✓ Historical Tracking

✓ Search Engine

✓ Recommendation Engine

✓ Data Warehouse

---

# Data Flow

```text
Raw Data
    ↓

Staging

    ↓

3NF Database

    ↓

Data Warehouse

    ↓

Data Mart

    ↓

Power BI
Search API
Recommendation API
Web Portal
```

---

# Summary

Operational Database là "single source of truth" của toàn bộ hệ thống.

Tất cả:

* Lifecycle
* Deduplication
* Search
* Recommendation
* Analytics

đều được xây dựng từ tầng dữ liệu này trước khi đổ sang Data Warehouse.
