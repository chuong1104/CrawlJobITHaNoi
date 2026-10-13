# JobITVN Data Platform — Master Documentation & Project Guide

## 1. Tổng Quan Dự Án (Overview)

**JobITVN Data Platform** là nền tảng Data Engineering & Analytics toàn diện mô phỏng môi trường sản xuất (Enterprise Grade), chuyên thu thập, làm sạch, chuyển đổi, lưu trữ và trực quan hóa dữ liệu thị trường tuyển dụng Công nghệ Thông tin tại Việt Nam.

Dự án đặc biệt chú trọng vào phân khúc ứng viên trẻ:
* **Intern / Thực tập sinh**
* **Fresher / Mới tốt nghiệp**
* **Junior / Entry Level (< 2 năm kinh nghiệm)**
* **Việc làm IT Part-time / Remote / Không yêu cầu kinh nghiệm**

Dữ liệu được thu thập tự động hàng ngày từ **8 cổng tuyển dụng hàng đầu** tại Việt Nam: **TopCV, ITviec, VietnamWorks, LinkedIn, CareerViet, JobsGO, Joboko, 123Job**.

---

## 2. Kiến Trúc Hệ Thống (Architecture Blueprint)

Hệ thống tuân thủ nghiêm ngặt mô hình **Medallion Architecture (Lakehouse) kết hợp Operational Data Store (3NF) & Kimball Star Schema (DWH)**:

```text
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                    8 Active Portals (TopCV, ITviec, LinkedIn,...)           │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ Scrapling TLS/JA4 + Playwright Sessions
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │ BRONZE LAYER: Raw Data Lake (Floci S3 / Local JSONL Fallback)               │
 │ • Schema-on-read, JSONL & Delta Table, partition: year/month/day            │
 │ • Pydantic v2 Contract Validation, Content Hash & Reject Queue              │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ dbt-duckdb (Smart Fallback: S3 -> Local)
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │ STAGING & INTERMEDIATE (DuckDB In-Memory)                                   │
 │ • 8 staging models (stg_topcv, stg_itviec, stg_linkedin,...)                │
 │ • int_all_jobs_unioned (Union 8 nguồn) + int_deduped_jobs                   │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ Python Sync Engine (DuckDB -> Postgres)
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │ SILVER LAYER: Operational Data Store (PostgreSQL 17 - 3NF)                  │
 │ • Tables: jobs, companies, job_snapshots, skills, locations                 │
 │ • Stored Procedures: SCD Type 2 tracking, Cross-source Fuzzy Dedup          │
 │ • CDC Watermark Tracker (last_sync_at) & Anomaly Detection                  │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │ PostgreSQL Stored Procedures / Views
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │ GOLD LAYER: Data Warehouse & Marts                                          │
 │ • Kimball Star Schema: fct_job_postings, fct_job_skills, dim_date, dim_*    │
 │ • Materialized Views: mv_kpi_realtime, mv_salary_by_skill, mv_active_jobs   │
 │ • S3 Parquet Delta Marts: mart_bi, mart_ml (GoldExporter)                   │
 └───────────────────┬─────────────────────────────────────┬───────────────────┘
                     │                                     │
                     ▼                                     ▼
 ┌───────────────────────────────────────┐ ┌───────────────────────────────────┐
 │ SERVING LAYER: FastAPI + Dark Web UI │ │ ANALYTICS LAYER: Power BI         │
 │ • SQLAlchemy QueuePool (5/10)         │ │ • Star Schema DirectQuery / Import│
 │ • In-Memory TTL Cache (@ttl_cache)    │ │ • Phân tích xu hướng kỹ năng,     │
 │ • GIN Trigram Search (<50ms)          │ │   mức lương & địa lý              │
 │ • Serverless on Vercel (api/index.py) │ └───────────────────────────────────┘
 └───────────────────────────────────────┘
```

---

## 3. Danh Mục Tài Liệu Kỹ Thuật (Master Documentation Index)

Dưới đây là toàn bộ các tài liệu kỹ thuật chi tiết của dự án trong thư mục `docs/`:

### Kiến Trúc & Thiết Kế Hệ Thống
1. [01. Vấn Đề Nghiệp Vụ & Bối Cảnh Thị Trường](file:///d:/JobITVN/job_scraper_de_project/docs/01_business_problem.md) — Phân tích nỗi đau thị trường, bài toán dữ liệu phân mảnh, dải lương và yêu cầu kinh nghiệm.
2. [02. Kiến Trúc Hệ Thống Tổng Thể](file:///d:/JobITVN/job_scraper_de_project/docs/02_system_architecture.md) — Chi tiết luồng dữ liệu end-to-end, Medallion Architecture và tương tác giữa các service.
3. [03. Danh Mục Công Nghệ & Tiêu Chí Lựa Chọn](file:///d:/JobITVN/job_scraper_de_project/docs/03_technology_stack.md) — Phân tích lý do chọn DuckDB thay Spark, PostgreSQL 17 thay MySQL, Floci S3, dbt và Scrapling.
4. [20. Data Platform Blueprint Toàn Diện](file:///d:/JobITVN/job_scraper_de_project/docs/20_data_platform_blueprint.md) — Tài liệu thiết kế hệ thống chi tiết (13 chương): từ Data Contracts, CDC Watermark, Cross-source Dedup, Data Quality đến kỹ thuật tối ưu DE.
5. [project_structure.md: Tài Liệu Cấu Trúc Mã Nguồn](file:///d:/JobITVN/job_scraper_de_project/docs/project_structure.md) — Giải thích chi tiết chức năng của từng file, folder và script trong dự án.
6. [10. Cấu Trúc Thư Mục Dự Án](file:///d:/JobITVN/job_scraper_de_project/docs/10_project_structure.md) — Sơ đồ cây thư mục kỹ thuật của source code và dbt models.

### Thu Thập & Lưu Trữ Dữ Liệu (Ingestion & Storage)
7. [05. Cơ Sở Dữ Liệu Vận Hành Silver 3NF](file:///d:/JobITVN/job_scraper_de_project/docs/05_operational_database_3nf.md) — Thiết kế ODS PostgreSQL chuẩn 3NF, ràng buộc khóa ngoại, quản lý SCD Type 2 và Stored Procedures.
8. [06. Kiến Trúc Delta Lakehouse](file:///d:/JobITVN/job_scraper_de_project/docs/06_data_lakehouse.md) — Quản lý Bronze Delta Table trên Floci S3, giao dịch ACID, schema evolution và Time Travel.
9. [21. Quản Lý Vòng Đời Tin Tuyển Dụng & Schema DWH](file:///d:/JobITVN/job_scraper_de_project/docs/21_job_lifecycle_and_schema_design.md) — Quản lý 9 trạng thái vòng đời job (NEW, ACTIVE, CLOSED,...), mã vân tay kép SHA-256 (`identity_hash` & `content_hash`).

### Xử Lý & Chuyển Đổi Dữ Liệu (Transformation & Orchestration)
10. [07. Thiết Kế Data Marts](file:///d:/JobITVN/job_scraper_de_project/docs/07_data_marts.md) — Thiết kế các Data Marts: `mart_bi` (Power BI), `mart_api` (FastAPI), `mart_ml` (Machine Learning).
11. [08. Quy Trình Xử Lý Dữ Liệu ELT](file:///d:/JobITVN/job_scraper_de_project/docs/08_data_pipeline.md) — Chi tiết các bước chuyển đổi dữ liệu từ Bronze sang Silver ODS và Gold DWH qua dbt + DuckDB.
12. [09. Điều Phối Tự Động Hóa Với Apache Airflow](file:///d:/JobITVN/job_scraper_de_project/docs/09_airflow_orchestration.md) — Cấu hình DAG `daily_job_pipeline`, PythonOperator Smart Fallback, TaskGroups, SLA và cơ chế retry.

### Phục Vụ & Trực Quan Hóa Dữ Liệu (Serving & BI)
13. [22. Tầng Phục Vụ Dữ Liệu & Visualization](file:///d:/JobITVN/job_scraper_de_project/docs/22_serving_layer_and_visualization.md) — Tổng quan Serving layer: FastAPI, SQLAlchemy QueuePool, In-Memory TTL Cache và Power BI connection.
14. [23. Triển Khai Giao Diện Web & FastAPI](file:///d:/JobITVN/job_scraper_de_project/docs/23_fastapi_web_portal_implementation.md) — Hướng dẫn mã nguồn chi tiết Backend FastAPI và Dashboard Dark Mode Glassmorphism.
15. [power_bi_integration_guide.md: Cẩm Nang Power BI](file:///d:/JobITVN/job_scraper_de_project/docs/power_bi_integration_guide.md) — Hướng dẫn kết nối ODBC DirectQuery/Import, mô hình hóa Star Schema và xây dựng biểu đồ DAX.

### Tối Ưu Hóa & Vận Hành Hạ Tầng (DevOps & Optimization)
16. [RAM_OPTIMIZATION_STRATEGY.md: Chiến Lược Tối Ưu RAM](file:///d:/JobITVN/job_scraper_de_project/docs/RAM_OPTIMIZATION_STRATEGY.md) — Phân tích hiện trạng tài nguyên và đề xuất lộ trình tối ưu hóa bộ nhớ xuống ngưỡng ~1.5GB cho máy cá nhân yếu.
17. [24. Triển Khai Cloud Miễn Phí](file:///d:/JobITVN/job_scraper_de_project/docs/24_free_cloud_deployment_guide.md) — Hướng dẫn đưa toàn bộ pipeline lên Oracle Cloud Always Free (24GB RAM ARM) hoặc Vercel Serverless.
18. [docker_maintenance.md: Hướng Dẫn Bảo Trì Docker](file:///d:/JobITVN/job_scraper_de_project/docs/docker_maintenance.md) — Hướng dẫn dọn dẹp tài nguyên Docker và nén file `.vhdx` WSL2 để thu hồi ổ cứng.

### AI / Machine Learning & Nghiên Cứu
19. [11. Hướng Dẫn Fine-Tuning LLM & AI](file:///d:/JobITVN/job_scraper_de_project/docs/11_llm_finetune_guide.md) — Chuẩn bị tập dữ liệu tuyển dụng chuẩn và huấn luyện mô hình ngôn ngữ hỗ trợ tư vấn nghề nghiệp.

---

## 4. Hướng Dẫn Khởi Chạy Nhanh (Quick Start)

### 4.1. Khởi chạy toàn bộ hệ thống bằng Docker Compose

```bash
# 1. Sao chép và cấu hình file môi trường
cp .env.example .env

# 2. Khởi động PostgreSQL, Floci S3, Airflow 2.10 và FastAPI Web
docker-compose up -d

# 3. Kiểm tra các dịch vụ đang chạy:
# • Airflow Webserver: http://localhost:8080 (airflow / airflow)
# • Web Dashboard & API: http://localhost:8000
# • API Docs (Swagger): http://localhost:8000/docs
# • Floci S3 Mock UI: http://localhost:4566
```

### 4.2. Chạy thử nghiệm Crawler đơn lẻ trên máy Local

```bash
# Cài đặt thư viện
pip install -r requirements.txt

# Chạy toàn bộ 8 scrapers một lần
python scripts/run_all_scrapers.py
```

### 4.3. Chạy biến đổi dữ liệu dbt

```bash
cd dbt_jobitvn
dbt run
dbt test
```
