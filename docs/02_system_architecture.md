# System Architecture: Modern Data Stack Local & AWS Mock

## Overview

JobITVN Data Platform được thiết kế theo kiến trúc **Modern Data Stack** kết hợp **Local AWS Lakehouse**. Kiến trúc này giả lập hoàn hảo môi trường AWS trên máy cá nhân thông qua **Floci (S3 Mock)**, giúp hệ thống vừa dễ dàng đưa lên Cloud thật, vừa phân tích siêu tốc nhờ DuckDB, lại đáp ứng API Web nhanh chóng nhờ PostgreSQL.

Mục tiêu kiến trúc:

*   Xây dựng mô hình End-to-End Pipeline hoàn chỉnh trên máy cá nhân với Storage là S3 Data Lake (qua Floci).
*   Phân tách rõ ràng giữa Storage (Floci S3), Compute/OLAP (DuckDB), và OLTP/Serving (PostgreSQL).
*   Áp dụng dbt để quản lý luồng chuyển đổi dữ liệu một cách chuyên nghiệp.
*   Linh hoạt giữa việc query từ file cục bộ để tối ưu I/O hoặc query từ S3 để chuẩn hóa Cloud-Native.

---

# 1. High Level Architecture

```text
                    ┌─────────────────────┐
                    │  Job Websites       │
                    │---------------------│
                    │ ITviec, TopCV,      │
                    │ VietnamWorks, ...   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Crawling Layer      │
                    │ (Python/Playwright) │
                    └──────────┬──────────┘
                               │ (boto3 / Local Disk)
                               ▼
        ┌───────────────────────────────────────────────┐
        │        DATA LAKE STORAGE (Floci S3)           │
        │                                               │
        │  [Bronze]        [Silver]         [Gold]      │
        │ (JSONL/Delta)    (Delta)          (Delta)     │
        └──────────────────────▲────────────────────────┘
                               │ 
            (S3 Sync / local read_json for speed)
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Compute & Transform│
                    │    (dbt + DuckDB)   │
                    │  [Staging & DWH]    │
                    └──────────┬──────────┘
                               │
                               ▼
        ┌──────────────────────┴──────────────────────┐
        │                 Data Sync                   │
        │        (Python PostgreSQL Adapter)          │
        └──────┬───────────────────────────────┬──────┘
               │                               │
               ▼                               ▼
    ┌────────────────────┐          ┌────────────────────┐
    │     OLTP & API     │          │    OLAP & BI       │
    │   (PostgreSQL)     │          │    (DuckDB)        │
    │  [Silver / Gold]   │          │  [jobitvn.duckdb]  │
    └──────────┬─────────┘          └──────────┬─────────┘
               │                               │
               ▼                               ▼
          FastAPI Web                      Power BI
           Dashboard                       Dashboard
```

---

# 2. Architectural Principles

## Data Lakehouse Paradigm & Separation of Storage and Compute
- **Storage:** Floci giả lập AWS S3 (`s3://jobit-bronze`, `s3://jobit-gold`). Dữ liệu thô (JSONL) và định dạng chuẩn (Delta Lake) đều được lưu tại đây làm Data Lake gốc.
- **Compute:** DuckDB (In-process OLAP engine) và dbt (Data Transformation). DuckDB thực hiện tính toán trên bộ nhớ. Trong môi trường Dev, DuckDB có thể đọc fallback từ file JSONL cục bộ để tránh thắt cổ chai network local, nhưng bản chất kiến trúc vẫn coi S3 là Single Source of Truth dài hạn.

## Decoupled Serving Layer
- **PostgreSQL:** Lưu trữ dữ liệu chuẩn hóa 3NF (Silver) và các view Materialized (Gold) để phục vụ API tìm kiếm, đòi hỏi concurrency cao.
- **DuckDB:** Lưu trữ mô hình Star Schema (Warehouse) phục vụ báo cáo BI, đòi hỏi khả năng tính toán Analytical (Group by, Aggregate) cực nhanh.

## Medallion Architecture
- **Bronze (Raw):** Dữ liệu JSONL nguyên bản từ crawler được upload lên Floci S3 bucket và ghi dạng Delta.
- **Silver (Cleaned & Standardized):** Dữ liệu được dbt làm sạch trong DuckDB, sau đó sync sang PostgreSQL lưu trữ theo chuẩn 3NF kèm SCD Type 2 (History).
- **Gold (Aggregated):** Dữ liệu tổng hợp tối ưu cho báo cáo BI (Star Schema trong DuckDB, đồng thời export ra S3 Delta) và tối ưu cho API (Materialized Views trong PostgreSQL).

---

# 3. Service Architecture

```text
job_scraper_de_project
│
├── crawler (Python)       # Thu thập dữ liệu: Scrapling HTTP (TLS/JA4 bypass) + Playwright (Cookie Session)
├── floci (LocalStack)     # Giả lập AWS S3, lưu trữ Bronze & Gold Delta Lake
├── airflow (Python)       # Điều phối Workflow hàng ngày (Airflow 2.10 Standalone, limit 4GB, reservation 1.5GB)
├── postgres (Docker)      # PostgreSQL 17: Silver 3NF ODS + Gold Kimball DWH + Materialized Views
├── dbt (SQL)              # Data Build Tool (Staging, Intermediate, Warehouse, Marts BI)
├── duckdb (In-process)    # Analytical In-Memory Vectorized Engine (delta_scan & OLAP)
├── fastapi (Python)       # Serving API (SQLAlchemy QueuePool + TTL Cache) + Web Portal
└── powerbi (Desktop)      # Visualization qua DirectQuery DWH hoặc ODBC DuckDB
```

---

# 4. Crawling & Storage Layer

Thu thập dữ liệu từ 8+ website tuyển dụng (TopCV, ITviec, VietnamWorks, LinkedIn, CareerViet, JobsGO, Joboko, 123job), lưu đệm ra ổ cứng dưới dạng JSONL, sau đó upload lên **Floci S3** và ghi dưới định dạng **Delta Lake** (`python-deltalake`) thông qua lớp quản lý `BronzeManager` và `DeltaLakeManager`.

```text
Website ──> Scraper (Scrapling/Playwright) ──> Local JSONL (Cache) ──> S3 / Delta Lake (Floci)
```

---

# 5. Tầng Transform: DuckDB + dbt

Đây là lõi xử lý dữ liệu của hệ thống.

## 5.1 Tầng Data Lake & Smart Fallback
Hồ dữ liệu chính được lưu tại S3 Floci (`s3://jobit-bronze`) dưới định dạng Delta Lake/Parquet. 
Để đảm bảo tính linh hoạt tối đa khi chạy:
* **Chế độ ưu tiên (`s3_parquet`):** `dbt` và `DuckDB` đọc trực tiếp các tệp Parquet/Delta trên S3 Floci qua `delta_scan()` hoặc S3 extension.
* **Cơ chế Fallback thông minh (`local_jsonl`):** Nếu S3 chưa có tệp Parquet hoặc gặp sự cố kết nối, pipeline tự động chuyển sang đọc các tệp JSONL đệm cục bộ (`read_json_auto`) mà không làm gián đoạn luồng công việc.

## 5.2 Tầng Compute: DuckDB
DuckDB đóng vai trò In-Memory Vectorized Engine: đọc dữ liệu siêu tốc vào RAM, thực hiện parse regex (mức lương, số năm kinh nghiệm, chuẩn hóa kỹ năng) và tạo file database `jobitvn.duckdb` chứa các bảng Staging, Intermediate và Warehouse.

## 5.3 Tầng Transformation: dbt
*   **Staging Models (`staging/`):** 8 models tương ứng 8 nguồn tuyển dụng (`stg_topcv`, `stg_itviec`, `stg_vietnamworks`, `stg_linkedin`, `stg_careerviet`, `stg_jobsgo`, `stg_joboko`, `stg_123job`), làm sạch và cast type.
*   **Intermediate Models (`intermediate/`):** Union 8 nguồn (`int_all_jobs_unioned`), dedup nội bộ (`int_deduped_jobs`), bóc tách kỹ năng (`int_job_skills_exploded`), và phát hiện biến động (`int_changed_jobs`).
*   **Warehouse Models (`marts/warehouse/`):** Fact & Dimensions (Kimball Star Schema).
*   **BI Marts (`marts/mart_bi/`):** 10 models tổng hợp KPI, xu hướng kỹ năng, phân tích mức lương và việc làm theo địa phương.

---

# 6. Tầng Sync & PostgreSQL (Silver/Gold)

Để phục vụ cho Web API và Power BI, luồng đồng bộ (Sync Layer) được thực hiện tự động trong Airflow:

## Silver Layer (PostgreSQL)
*   Sử dụng thuật toán **CDC Watermark** (`silver.cdc_watermarks`) để chỉ đồng bộ những bản ghi mới từ DuckDB sang Postgres.
*   Chuẩn hóa 3NF: tách `jobs`, `companies`, `skills`, `locations`.
*   Giải quyết Alias Công ty qua `pg_trgm` (trigram fuzzy matching) và lưu vết lịch sử biến động việc làm qua SCD Type 2 (`silver.job_snapshots`).
*   Phát hiện và gom nhóm tin trùng lặp cross-source (`JobDedupEngine`).

## Gold Layer (PostgreSQL & S3)
*   **Postgres:** Sử dụng Stored Procedures (`dwh.sp_sync_*`) để đồng bộ từ Silver sang Gold Star Schema (`dwh.fct_job_posting`, `dwh.dim_*`) và refresh các **Materialized Views** (`mv_active_jobs_summary`, `mv_kpi_realtime`, `mv_salary_by_skill`, `mart_api.latest_jobs_flat`) phục vụ Web API (<50ms).
*   **S3 Delta Lake:** `GoldExporter` export các bảng Data Mart (`mart_bi`, `mart_ml`) ra định dạng Delta Lake lên S3 (`s3://jobit-gold`) và Parquet phục vụ Machine Learning và Power BI.

---

# 7. Airflow Orchestration

Airflow điều phối luồng chạy hàng ngày (Daily DAG `@ 06:00 AM`) với cấu trúc phân nhánh song song tối ưu:

```text
        ┌───────────┐
        │   start   │
        └─────┬─────┘
              ▼
  ┌───────────────────────┐
  │   crawl_all_sources   │ (Chạy song song 8 scrapers, metrics -> XCom)
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │    run_dbt_staging    │ (Smart Fallback: S3 Parquet -> JSONL local)
  └─────┬───────────┬─────┘
        │           ├──────────────────────────────┐
        ▼           ▼                              ▼
  ┌───────────┐ ┌───────────────────┐      ┌─────────────────────┐
  │run_dbt_gol│ │ sync_silver_layer │      │ archive_bronze_data │ (Gom nén JSON > 30 ngày)
  └─────┬─────┘ └─────────┬─────────┘      └──────────┬──────────┘
        │                 ▼                           │
        │       ┌───────────────────┐                 │
        │       │sync_postgres_gold │                 │
        │       └─────────┬─────────┘                 │
        │                 ▼                           │
        │       ┌───────────────────┐                 │
        │       │ export_gold_marts │                 │
        │       └─────────┬─────────┘                 │
        ▼                 ▼                           │
  ┌─────┴─────────────────┴─────┐                     │
  │    vacuum_delta_tables      │ (VACUUM Delta Tables)│
  └──────────────┬──────────────┘                     │
                 ▼                                    │
           ┌───────────┐                              │
           │    end    │◀─────────────────────────────┘
           └───────────┘
```

---

# 8. Tại sao kiến trúc này tối ưu?

1. **Cloud-Ready (Sẵn sàng lên Cloud):** Mọi giao tiếp với Data Lake đều thông qua chuẩn `boto3` cắm vào Floci S3. Khi dự án cần deploy lên AWS thật, chỉ cần đổi endpoint S3 là hệ thống chạy y chang.
2. **Hiệu năng tối đa, Chi phí tối thiểu:** Phân tách rõ nhiệm vụ: DuckDB gánh Analytic cho PowerBI, Postgres gánh lượng truy cập đồng thời lớn cho Web API. Tất cả chạy mượt mà ngay trên máy cá nhân mà không tốn chi phí thuê Cloud.
