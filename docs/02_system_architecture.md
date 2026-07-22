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
job-it-platform
│
├── crawler (Python)       # Job thu thập dữ liệu bằng Playwright
├── floci (LocalStack)     # Giả lập AWS S3, nơi lưu trữ Data Lake chính yếu
├── airflow (Python)       # Điều phối Workflow hàng ngày
├── postgres (Docker)      # Database phục vụ API Web
├── dbt (SQL)              # Data Build Tool (Transform)
├── duckdb (In-process)    # Analytical Query Engine (Được Airflow/PowerBI gọi)
├── fastapi (Python)       # Serving API
└── powerbi (Desktop)      # Visualization qua ODBC kết nối DuckDB
```

---

# 4. Crawling & Storage Layer

Thu thập dữ liệu từ các website tuyển dụng, lưu tạm ra ổ cứng dưới dạng JSONL, sau đó upload ngay lên **Floci S3** và ghi đè dưới định dạng **Delta Lake** thông qua lớp quản lý `BronzeManager` và `DeltaLakeManager`.

```text
Website ──> Scraper (Playwright/Scrapy) ──> Local JSONL (Cache) ──> S3 / Delta Lake (Floci)
```

---

# 5. Tầng Transform: DuckDB + dbt

Đây là lõi xử lý dữ liệu của hệ thống.

## 5.1 Tầng Data Lake & Cache
Mặc dù Data Lake chính nằm trên S3 (Floci), để tối ưu độ trễ I/O trong quá trình chuyển đổi, `dbt` được cấu hình đọc trực tiếp các file JSONL cache ở local (`read_json_auto`).

## 5.2 Tầng Compute: DuckDB
DuckDB dùng extension `json` để đọc hàng ngàn file JSONL vào RAM, thực hiện parse bằng regex (ví dụ: bóc tách số năm kinh nghiệm, mức lương) cực nhanh. DuckDB cũng tạo file database `jobitvn.duckdb` chứa các bảng Staging và Warehouse.

## 5.3 Tầng Transformation: dbt
*   **Staging Models:** Làm sạch dữ liệu, chuẩn hóa tên cột, parse thông tin JSON text.
*   **Warehouse Models:** Xây dựng Fact/Dim tables (Mô hình sao).

---

# 6. Tầng Sync & PostgreSQL (Silver/Gold)

Để phục vụ cho Web API, một luồng đồng bộ (Sync Layer) được thực hiện bằng Python trong Airflow:

## Silver Layer (PostgreSQL)
*   Sử dụng thuật toán **CDC Watermark** để chỉ đồng bộ những bản ghi mới từ DuckDB sang Postgres.
*   Giải quyết Alias Công ty và theo dõi sự thay đổi của tin tuyển dụng qua SCD Type 2 (`job_snapshots`).

## Gold Layer (PostgreSQL & S3)
*   **Postgres:** Sử dụng Stored Procedure để refresh các **Materialized Views** (`mv_kpi_realtime`, `latest_jobs_flat`) phục vụ Web.
*   **S3:** `DeltaLakeManager` export các bảng báo cáo ra định dạng Delta Lake lên S3 (`s3://jobit-gold`) để dành cho Model Machine Learning sau này.

---

# 7. Airflow Orchestration

Airflow điều phối luồng chạy hàng ngày (Daily DAG) với các nhánh chạy song song để tối ưu hóa thời gian:

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
 │dbt_gold   │ │sync_silv │         │archive_bronze   │
 └─────┬─────┘ └─────┬────┘         └────────┬────────┘
       │             ▼                       │
       │       ┌──────────┐                  │
       │       │sync_gold │                  │
       │       └─────┬────┘                  │
       │             ▼                       │
       │       ┌──────────┐                  │
       │       │export_mar│                  │
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

---

# 8. Tại sao kiến trúc này tối ưu?

1. **Cloud-Ready (Sẵn sàng lên Cloud):** Mọi giao tiếp với Data Lake đều thông qua chuẩn `boto3` cắm vào Floci S3. Khi dự án cần deploy lên AWS thật, chỉ cần đổi endpoint S3 là hệ thống chạy y chang.
2. **Hiệu năng tối đa, Chi phí tối thiểu:** Phân tách rõ nhiệm vụ: DuckDB gánh Analytic cho PowerBI, Postgres gánh lượng truy cập đồng thời lớn cho Web API. Tất cả chạy mượt mà ngay trên máy cá nhân mà không tốn chi phí thuê Cloud.
