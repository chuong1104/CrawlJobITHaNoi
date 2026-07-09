# Data Pipeline Design (Medallion ELT Pipeline v2.1)

## Overview

Data Pipeline là xương sống của JobITVN. Trong kiến trúc hiện tại, chúng ta áp dụng mô hình **ELT** (Extract, Load, Transform) kết hợp giữa hồ dữ liệu (Delta Lake) và cơ sở dữ liệu quan hệ (PostgreSQL) để tối ưu hóa hiệu năng, tính toàn vẹn nghiệp vụ và phục vụ phân tích.

1. **Extract & Load (E & L):** Scrapers cào dữ liệu và ghi trực tiếp vào **Bronze Delta Tables** trên S3 (Floci) thông qua `BronzeManager`.
2. **Transform (T - dbt staging):** Airflow kích hoạt `dbt` sử dụng DuckDB để đọc dữ liệu từ Bronze Delta Tables, làm sạch cơ bản, parse salary/skills và lưu vào DuckDB intermediate tables.
3. **Sync Silver & Gold (PostgreSQL & CDC):**
   - Python Sync Engine tải dữ liệu từ DuckDB intermediate tables vào bảng đệm `staging.stg_jobs`.
   - Chạy logic **CDC Watermark** để lọc dữ liệu cũ, chỉ nạp dữ liệu mới vào PostgreSQL Silver Layer (3NF).
   - Xử lý trùng lặp thực thể (company aliases) và cập nhật SCD Type 2 lịch sử tin tuyển dụng.
   - Gọi PostgreSQL stored procedures để đồng bộ dữ liệu Silver -> Gold DWH và refresh các **Materialized Views** phục vụ API/BI.
4. **Gold Export:** `GoldExporter` đọc DWH và ghi ra Delta tables trên S3 (`mart_bi`, `mart_ml`) đồng thời dọn dẹp (VACUUM) các tệp tin cũ.

---

# 1. Complete End-to-End Data Pipeline Flow

```text
┌──────────────────────────────────────────────────┐
│                   JOB PORTALS                    │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│       CRAWLER LAYER (Python, Playwright)         │
└────────────────────────┬─────────────────────────┘
                         │ Extract & Load (Delta Lake API)
                         ▼
┌──────────────────────────────────────────────────┐
│      BRONZE LAYER (S3 Delta Tables - Raw)        │
│   - Schema Evolution, ACID, Time Travel          │
└────────────────────────┬─────────────────────────┘
                         │
        dbt run (DuckDB delta_scan over S3)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│      STAGING MODELS (dbt View / Intermediate)    │
│   - Rename, Cast Types, Parse Salary/Skills      │
└────────────────────────┬─────────────────────────┘
                         │
      Bulk Insert (PostgreSQL staging.stg_jobs)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│     SILVER LAYER (PostgreSQL 3NF Schema)         │
│   - CDC Watermark Tracker (last_sync_at)         │
│   - Company Alias Resolution (Fuzzy Matching)    │
│   - SCD Type 2 History (job_snapshots)           │
└────────────────────────┬─────────────────────────┘
                         │
     SQL Stored Procedures (dwh.* Schema)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│   GOLD DWH (PostgreSQL) + MATERIALIZED VIEWS      │
│   - fact_job_posting, dim_company, dim_skill     │
│   - mv_active_jobs_summary, mv_kpi_realtime      │
└────────────────────────┬─────────────────────────┘
                         │
    GoldExporter (PostgreSQL DWH -> S3 Delta)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│      GOLD DATA MARTS (S3 Delta Tables)           │
│   - s3://jobit-gold/gold/mart_bi/                │
│   - s3://jobit-gold/gold/mart_ml/                │
└───────┬────────────────────┬─────────────────┬───┘
        │                    │                 │
        ▼                    ▼                 ▼
    Power BI             FastAPI API        ML Model
  (Delta Scan)         (Materialized View) (Feature Store)
```

---

# 2. CDC Watermark & Anomaly Detection

Nhằm giải quyết vấn đề quá tải database nghiệp vụ khi chạy batch hàng ngày, cơ chế **Change Data Capture (CDC)** dựa trên watermark đã được tích hợp:

1. **Watermark tracking (`silver.cdc_watermarks`):**
   - Hệ thống lưu lại timestamp của lần sync thành công gần nhất cho từng nguồn (`last_sync_at`).
   - Lần sync tiếp theo, dbt intermediate chỉ lấy các bản ghi có `scraped_at > last_sync_at`.
2. **Pipeline Logging (`silver.pipeline_run_log`):**
   - Mọi pipeline run đều được log trạng thái (RUNNING, SUCCESS, FAILED), thời gian chạy, số lượng bản ghi mới/cũ/reject.
3. **Phát hiện Anomaly (Cảnh báo block):**
   - Mỗi portal có một `expected_min_count` (số lượng tin tuyển dụng tối thiểu mong đợi mỗi ngày).
   - Nếu `new_records < expected_min_count * 50%`, hệ thống bật cờ `anomaly_flag = TRUE` và log lý do (cảnh báo scraper có thể bị chặn hoặc trang web nguồn thay đổi giao diện).
   - Nếu liên tiếp 3 ngày có cờ cảnh báo (`consecutive_low_runs >= 3`), Airflow sẽ đưa cảnh báo CRITICAL.

---

# 3. Gold Layer & Materialized Views Optimization

Để tối ưu hóa thời gian phản hồi của APIs và tăng tốc độ vẽ báo cáo trong Power BI:
- Bảng Fact `dwh.fct_job_posting` liên kết với các bảng Dimensions thông qua mô hình Star Schema.
- 4 **Materialized Views** được tạo sẵn trong PostgreSQL và được cấu hình cơ chế `REFRESH MATERIALIZED VIEW CONCURRENTLY` (không lock bảng đọc):
  1. `dwh.mv_active_jobs_summary`: Cache toàn bộ jobs đang active cùng thông tin công ty phục vụ cho FastAPI.
  2. `dwh.mv_kpi_realtime`: Cache 12 KPI của Semantic Layer, loại bỏ các phép tính đếm/tổng hợp phức tạp trên bảng Fact.
  3. `dwh.mv_salary_by_skill`: Tính toán lương trung bình, median, và rank cho từng kỹ năng.
  4. `dwh.mv_jobs_by_location`: Thống kê việc làm theo khu vực địa lý phục vụ sơ đồ bản đồ BI.

---

# 4. Airflow DAG Workflow (Daily Execution Pipeline)

Mỗi ngày lúc 6h sáng, Airflow kích hoạt pipeline và giám sát luồng chạy:

```text
┌────────────────┐
│     start      │
└───────┬────────┘
        │
        ▼
┌───────────────────────┐
│   crawl_all_sources   │  (Scrape dữ liệu -> ghi Delta Bronze trên S3)
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│    run_dbt_staging    │  (dbt: Staging & Intermediate DuckDB)
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│   sync_silver_layer   │  (Python: Postgres 3NF + SCD Type 2 + CDC Watermark)
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│     run_gold_dwh      │  (Python: Stored Procs update DWH + Refresh MVs)
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│   export_gold_marts   │  (Python: Export Gold DWH -> Delta Tables trên S3)
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│  vacuum_delta_tables  │  (Delta Maintenance: Xóa log/files cũ > 7 ngày)
└───────┬───────────────┘
        │
        ▼
┌────────────────┐
│      end       │
└────────────────┘
```
- **Idempotency (Tính khả trùng):** Nếu pipeline bị ngắt quãng giữa chừng, việc chạy lại (re-run) hoàn toàn không gây trùng lặp bản ghi hay sai lệch metrics nhờ vào định danh duy nhất `job_id` (SHA-256 từ URL và source) kết hợp với các câu lệnh `ON CONFLICT DO UPDATE` ở Silver layer và ghi đè Delta tables ở Gold layer.
