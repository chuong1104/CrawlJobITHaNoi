# JobITVN Data Platform

## Overview

JobITVN Data Platform là một dự án Data Engineering mô phỏng hệ thống thu thập, xử lý, phân tích và phục vụ dữ liệu tuyển dụng dành cho sinh viên và người ít kinh nghiệm trong lĩnh vực Công nghệ Thông tin tại Việt Nam.

Dự án tập trung vào các vị trí:

* Intern
* Fresher
* Entry Level
* Không yêu cầu kinh nghiệm
* Part-time IT
* Student-friendly jobs

Dữ liệu được thu thập từ nhiều nền t năng tuyển dụng phổ biến tại Việt Nam, sau đó được xử lý thông qua kiến trúc Data Platform hoàn chỉnh gồm:

* Data Collection
* Delta Lakehouse
* Operational ODS (PostgreSQL 3NF)
* ETL / ELT (dbt)
* Data Warehouse (Star Schema)
* Data Mart (Delta Lake & Materialized Views)
* dbt Semantic Layer
* Airflow Orchestration

Mục tiêu của dự án là xây dựng một hệ thống tiệm cận môi trường doanh nghiệp thực tế.

---

# Business Problem

Sinh viên ngành:

* Công nghệ Thông tin
* Khoa học Máy tính
* Data Science
* Data Engineering
* AI / Machine Learning

thường gặp nhiều khó khăn trong việc tìm kiếm cơ hội:

* Thực tập
* Fresher
* Không yêu cầu kinh nghiệm
* Việc làm thêm liên quan đến CNTT

Thông tin tuyển dụng hiện đang phân tán trên nhiều nền tảng (ITviec, TopCV, VietnamWorks, CareerViet, JobsGO, JobOKO, LinkedIn, Job123). Người tìm việc phải truy cập từng nền tảng riêng lẻ.

Dự án xây dựng một nền tảng dữ liệu tập trung giúp cào và tổng hợp từ 8 nguồn chính trên.
* Tổng hợp dữ liệu tuyển dụng
* Loại bỏ dữ liệu trùng lặp (Entity & Company Alias resolution)
* Theo dõi vòng đời việc làm
* Phân tích xu hướng tuyển dụng
* Hỗ trợ tìm kiếm thông minh
* Hỗ trợ gợi ý việc làm phù hợp

---

# Project Goals

## Data Engineering

Xây dựng hệ thống Data Engineering hoàn chỉnh bao gồm:

* Web Crawling
* Delta Lake (ACID, Schema Evolution, Time Travel)
* PostgreSQL 3NF ODS & Stored Procedures
* Data Warehouse (Star Schema)
* PostgreSQL Materialized Views (Tối ưu serving)
* dbt Semantic Layer (Metrics định nghĩa tập trung)
* Airflow Orchestration & Delta Vacuuming
* Data Quality & Schema Drift Validation
* CDC Delta-Load dựa trên Watermark
* Anomaly Detection (Phát hiện chặn crawler)
* SCD Type 2 & Trigram Alias lookup

## Analytics

Phân tích:
* Nhu cầu tuyển dụng theo kỹ năng (Xu hướng tăng trưởng WoW, Rolling 4w)
* Nhu cầu tuyển dụng theo thành phố
* Xu hướng tuyển dụng theo thời gian
* Lương theo vai trò và kỹ năng
* Chất lượng dữ liệu theo nguồn

---

# High Level Architecture

```text
Job Websites
      │
      ▼
Web Crawlers (Python / Playwright)
      │
      ▼
Raw Data Lake (Floci S3 - Bronze Layer - Delta Table Format)
      │
      ├── dbt run (DuckDB delta_scan over S3)
      ▼
Intermediate (DuckDB tables)
      │
      ├── Python Sync Engine & CDC Watermark Tracker
      ▼
Silver Layer (PostgreSQL 3NF Operational DB - SCD Type 2)
      │
      ├── Stored Procedures (dwh.* schema)
      ▼
Gold Layer (PostgreSQL DWH + Materialized Views serving API)
      │
      ├── GoldExporter (DWH -> S3 Delta Tables)
      ▼
Gold Data Marts (Floci S3 - Gold Layer - Delta format)
      │
      ├── Power BI Dashboard (Delta Scan)
      ├── FastAPI Serving (Materialized Views)
      └── ML/RAG Models (Delta Table Features)
```

---

# Technology Stack

## Data Collection

* Python (Scrapling, Playwright, BeautifulSoup)

## Storage & Data Lake

* **Delta Lake (via python-deltalake)**
* **PostgreSQL** (Operational Silver 3NF ODS, DWH Schema & Airflow Metadata)
* Floci S3 (AWS S3 Mock Server)

## Data Processing & Transformation

* dbt-core (với plugins `dbt-duckdb` & `dbt-postgres`)
* **dbt Semantic Layer (MetricFlow)**
* DuckDB (Query Engine xử lý Delta S3 trực tiếp)
* Python (pandas, psycopg2, boto3)

## Orchestration & Cloud Simulation

* Apache Airflow
* Docker & Docker Compose
* Floci (Giả lập AWS Cloud)

## API & Serving

* FastAPI (kết nối PostgreSQL đọc **Materialized Views**)
* Power BI (kết nối DirectQuery vào DWH / delta_scan S3 Delta tables)

---

# Data Architecture

## Raw Layer (Bronze)
Lưu dữ liệu gốc cào về dạng **Delta Table** phân vùng theo `_batch_date`. Đảm bảo tính ACID của data lake, hỗ trợ schema evolution khi nguồn đổi cấu trúc, và Time Travel để khôi phục hoặc phân tích lịch sử.

## Staging Layer
Đọc từ Delta Bronze bằng DuckDB, đổi tên cột, cast kiểu dữ liệu và lưu thành các view hoặc bảng đệm staging.

## Silver Layer (PostgreSQL 3NF)
Operational database quan hệ giúp kiểm soát chặt chẽ ràng buộc khóa ngoại:
* Xử lý gom nhóm aliases (pg_trgm fuzzy matching) để giải quyết trùng lặp công ty.
* Theo dõi lịch sử thay đổi tin tuyển dụng bằng SCD Type 2 (`job_snapshots`).
* CDC Watermark tracking (`last_sync_at`) giúp giảm tải database và phát hiện anomaly khi crawler thu về ít dữ liệu đột biến.

## Gold Layer (DWH & Marts)
* **DWH Star Schema:** `fct_job_posting` liên kết với các bảng dimensions (`dim_company`, `dim_skill`, `dim_location`, `dim_date`, `dim_source`).
* **Materialized Views:** Pre-compute các báo cáo nặng (`mv_kpi_realtime`, `mv_salary_by_skill`) để tăng hiệu năng serving.
* **Delta Marts:** Export ra S3 dưới dạng Delta tables (`mart_bi`, `mart_ml`) phục vụ Power BI và AI/ML training.

---

## Bảo trì & Vận hành Hệ thống
* [Hướng dẫn Bảo trì & Tối ưu Dung lượng Docker (WSL2)](file:///d:/JobITVN/job_scraper_de_project/docs/docker_maintenance.md): Hướng dẫn chi tiết cách dọn dẹp tài nguyên Docker và nén file ổ đĩa ảo `.vhdx` để thu hồi dung lượng đĩa cứng trên Windows.

