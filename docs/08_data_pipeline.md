# Data Pipeline Design (Medallion ELT Pipeline v3.0)

## Overview

Data Pipeline là xương sống của dự án JobITVN. Trong kiến trúc hiện tại, chúng ta áp dụng mô hình **ELT** (Extract, Load, Transform) kết hợp giữa Data Lake (Floci S3), cơ sở dữ liệu OLAP cục bộ (DuckDB) và cơ sở dữ liệu OLTP/Serving (PostgreSQL).

1. **Extract & Load (E & L):** Scrapers cào dữ liệu thô, ghi file **JSONL (Bronze Layer)** cục bộ và đồng thời **upload lên S3 (Floci)** dưới dạng Delta Table.
2. **Transform (T - dbt trên DuckDB):** Airflow kích hoạt `dbt` sử dụng DuckDB để đọc file JSONL, làm sạch, parse mức lương và kinh nghiệm qua Regex, sau đó xây dựng các bảng Staging và Warehouse trực tiếp bên trong file database `jobitvn.duckdb` (Đọc từ local cache để tối ưu tốc độ xử lý).
3. **Sync Silver (PostgreSQL 3NF):** Python Sync Engine tải dữ liệu từ DuckDB vào bảng đệm `staging.stg_jobs`, sau đó sử dụng CDC Watermark để Upsert dữ liệu vào tầng Silver của PostgreSQL (mô hình 3NF, xử lý SCD Type 2).
4. **Gold Layer & MVs:** Các Stored Procedure chạy trong PostgreSQL để đồng bộ từ Silver lên Gold, tạo ra `latest_jobs_flat` và các `Materialized Views` phục vụ riêng cho Web API.

---

# 1. Complete End-to-End Data Pipeline Flow

```text
┌──────────────────────────────────────────────────┐
│                   JOB PORTALS                    │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│       CRAWLER LAYER (Python, Scrapling)          │
└────────────────────────┬─────────────────────────┘
                         │ Extract & Load
                         ▼
┌──────────────────────────────────────────────────┐
│     BRONZE LAYER (S3 Data Lake & Local JSONL)    │
│   - Floci S3: s3://jobit-bronze/                 │
│   - Local: data/bronze/{source}/                 │
└────────────────────────┬─────────────────────────┘
                         │
             dbt run (DuckDB read_json)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│      STAGING & WAREHOUSE (DuckDB jobitvn.duckdb) │
│   - Parse Salary, Experience (Regex)             │
│   - Build Staging & Intermediate models          │
└────────────────────────┬─────────────────────────┘
                         │
        Python Bulk Sync (Postgres staging.stg_jobs)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│     SILVER LAYER (PostgreSQL 3NF Schema)         │
│   - CDC Watermark Tracker (last_sync_at)         │
│   - Company Alias Resolution                     │
│   - SCD Type 2 History (job_snapshots)           │
└────────────────────────┬─────────────────────────┘
                         │
       SQL Stored Procedures (dwh / mart_api)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│   GOLD DWH (PostgreSQL) + MATERIALIZED VIEWS      │
│   - mart_api.latest_jobs_flat (For API)          │
│   - dwh.mv_active_jobs_summary, mv_kpi_realtime  │
└───────┬──────────────────────────────────────┬───┘
         │                                      │
         ▼                                      ▼
     Power BI (ODBC)                        FastAPI API
   (Read DuckDB DWH)                    (Read Postgres Gold)
```

---

# 2. CDC Watermark & Anomaly Detection

Cơ chế **Change Data Capture (CDC)** dựa trên watermark đã được tích hợp nhằm tối ưu hóa việc đồng bộ từ DuckDB sang Postgres:

1. **Watermark tracking (`silver.crawl_sessions`):** Lưu lại session, số tin quét được, số tin bị lỗi/validated.
2. **Watermark sync (`silver.cdc_watermarks`):** Lưu timestamp `last_sync_at`.
3. **Phát hiện Anomaly:** Nếu số tin mới quá thấp hoặc tỷ lệ reject quá cao, hệ thống bật cờ cảnh báo.

---

# 3. Gold Layer & Materialized Views Optimization

- **Tầng API (Postgres):** 
  - Tạo view `mart_api.latest_jobs_flat` đã được de-normalize, phục vụ web tìm kiếm siêu tốc.
  - Các `Materialized Views` như `dwh.mv_kpi_realtime` được tính toán trước để render KPI trên Dashboard ngay lập tức.
- **Tầng BI (DuckDB):** Power BI kết nối thẳng vào `jobitvn.duckdb` qua ODBC để phân tích Star Schema mà không làm nặng Postgres.
- **Tầng S3 (Floci):** Dữ liệu Gold cũng được đồng bộ ra S3 (Delta Format) qua `GoldExporter` để phục vụ Data Science (ML Models).

---

# 4. Airflow DAG Workflow (Daily Execution Pipeline)

Mỗi ngày lúc 6h sáng, Airflow kích hoạt pipeline và giám sát luồng chạy song song:

```text
       ┌───────────┐
       │   start   │
       └─────┬─────┘
             ▼
 ┌───────────────────────┐
 │   crawl_all_sources   │
 └───────────┬───────────┘
             ▼
 ┌───────────────────────┐
 │    run_dbt_staging    │
 └─────┬───────────┬─────┘
       │           ├─────────────────────────┐
       ▼           ▼                         ▼
 ┌───────────┐ ┌──────────┐         ┌─────────────────┐
 │run_dbt_gol│ │sync_silv │         │archive_bronze_da│
 └─────┬─────┘ └─────┬────┘         └────────┬────────┘
       │             ▼                       │
       │       ┌──────────┐                  │
       │       │sync_postg│                  │
       │       └─────┬────┘                  │
       │             ▼                       │
       │       ┌──────────┐                  │
       │       │export_gol│                  │
       │       └─────┬────┘                  │
       ▼             ▼                       │
 ┌─────┴─────────────┴────┐                  │
 │  vacuum_delta_tables   │                  │
 └───────────┬────────────┘                  │
             ▼                               ▼
       ┌───────────┐                   ┌───────────┐
       │    end    │                   │    end    │
       └───────────┘                   └───────────┘
```
