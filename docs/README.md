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

Dữ liệu được thu thập từ nhiều nền tảng tuyển dụng phổ biến tại Việt Nam, sau đó được xử lý thông qua kiến trúc Data Platform hoàn chỉnh gồm:

* Data Collection
* Data Lake
* ETL / ELT
* Data Warehouse
* Data Mart
* Search Engine
* Recommendation Engine
* BI Dashboard
* Web Application

Mục tiêu của dự án là xây dựng một hệ thống gần với môi trường Data Engineer thực tế thay vì chỉ thực hiện một bài toán ETL đơn lẻ.

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

Thông tin tuyển dụng hiện đang phân tán trên nhiều nền tảng:

* ITviec
* TopCV
* VietnamWorks
* CareerViet
* TopDev
* Glints
* JobsGO
* Vieclam24h
* JobOKO
* CareerLink
* YBOX
* Indeed
* Job123

Người tìm việc phải truy cập từng nền tảng riêng lẻ để tìm kiếm cơ hội phù hợp.

Dự án xây dựng một nền tảng dữ liệu tập trung giúp:

* Tổng hợp dữ liệu tuyển dụng
* Loại bỏ dữ liệu trùng lặp
* Theo dõi vòng đời việc làm
* Phân tích xu hướng tuyển dụng
* Hỗ trợ tìm kiếm thông minh
* Hỗ trợ gợi ý việc làm phù hợp

---

# Project Goals

## Data Engineering

Xây dựng hệ thống Data Engineering hoàn chỉnh bao gồm:

* Web Crawling
* Data Lake
* Data Warehouse
* Data Mart
* Airflow Orchestration
* Data Quality
* Incremental Load
* CDC
* SCD Type 2
* Monitoring

## Analytics

Phân tích:

* Nhu cầu tuyển dụng theo kỹ năng
* Nhu cầu tuyển dụng theo thành phố
* Xu hướng tuyển dụng theo thời gian
* Mức lương
* Chất lượng dữ liệu theo nguồn

## Product

Xây dựng:

* Search Engine
* Recommendation Engine
* Job Portal Website

---

# Data Sources

Nguồn dữ liệu:

* ITviec
* TopCV
* VietnamWorks
* CareerViet
* TopDev
* JobsGO
* Glints
* CareerLink
* Vieclam24h
* JobOKO
* YBOX
* Indeed
* Job123

Mỗi website có crawler riêng phù hợp với đặc điểm:

* Scrapy
* Playwright
* BeautifulSoup
* Requests

---

# High Level Architecture

```text
Job Websites
      │
      ▼
Web Crawlers (Python / Playwright)
      │
      ▼
Raw Data Lake (Floci S3 - Bronze Layer - JSON)
      │
      ▼
Data Processing & Transformation (dbt + DuckDB)
      │
      ├── Staging (DuckDB views/tables)
      ├── Silver (Cleaned - Parquet on Floci S3)
      └── Gold (Star Schema/Marts - Parquet on Floci S3)
            │
            ├── Power BI
            ├── Search API (FastAPI + DuckDB)
            └── Web Application
```

---

# Technology Stack

## Data Collection

* Python
* Scrapy
* Playwright
* BeautifulSoup
* Requests

## Storage & Data Lake

* Floci S3 (AWS S3 Mock Server)
* Parquet (Silver & Gold Layers)
* JSON (Bronze/Raw Layer)
* PostgreSQL (Chỉ dùng làm Database backend lưu metadata cho Apache Airflow)

## Data Processing & Transformation

* dbt-core (sử dụng plugin `dbt-duckdb`)
* DuckDB (Query Engine phân tích trực tiếp trên S3)
* Python (Pandas/boto3 cho Crawler & Script phụ trợ)

## Data Warehouse & Compute

* DuckDB (Kiến trúc In-Process Columnar analytical database)

## Orchestration

* Apache Airflow

## Containerization

* Docker
* Docker Compose

## Cloud Simulation

* Floci (Giả lập AWS S3, RDS, IAM)

## API & Serving

* FastAPI
* DuckDB (Python API)

## Dashboard & Analytics

* Power BI (Kết nối trực tiếp file Parquet / DuckDB)

## Search

* DuckDB Full Text Search / SQL Querying

## Monitoring

* Airflow Logs
* Custom Quality checks via dbt tests


---

# Data Architecture

## Raw Layer

Lưu dữ liệu gốc từ website:

* Raw HTML
* Raw JSON
* Crawl Metadata

Mục tiêu:

* Audit
* Reprocessing
* Debugging

---

## Staging Layer

Chuẩn hóa dữ liệu về một schema chung.

Ví dụ:

* title
* company
* salary
* location
* description

---

## Silver Layer

Database chuẩn hóa 3NF.

Các bảng chính:

* sources
* companies
* jobs
* job_snapshots
* skills
* locations
* job_events

Mục tiêu:

* Data cleansing
* Deduplication
* Lifecycle management

---

## Gold Layer

Data Warehouse dạng Star Schema.

Dimension:

* dim_company
* dim_location
* dim_skill
* dim_source
* dim_date

Fact:

* fact_job_posting

---

# Data Quality

Các vấn đề được xử lý:

## Duplicate Jobs

Một công việc có thể xuất hiện trên:

* TopCV
* ITviec
* VietnamWorks

Sử dụng:

* URL Matching
* Content Hash
* Similarity Matching

để gom nhóm duplicate.

---

## Job Expiration

Xác định:

* Active
* Expired
* Closed
* Reposted

thông qua:

* Expiration Date
* Crawl History
* Consecutive Missing Detection

---

## Content Changes

Phát hiện thay đổi:

* Title
* Salary
* Skills
* Requirements
* Description

bằng Content Hash và Snapshot Tracking.

---

# Search Engine

Hỗ trợ tìm kiếm:

Ví dụ:

```text
etl
```

Kết quả có thể trả về:

* Data Engineer Intern
* Data Pipeline Intern
* BI Developer Intern

Tìm kiếm dựa trên:

* Job Title
* Skills
* Description
* Synonym Dictionary

---

# Recommendation Engine

Gợi ý việc làm dựa trên:

* Kỹ năng
* Sở thích
* Vị trí địa lý
* Kinh nghiệm

Các phương pháp:

* Rule Based Recommendation
* Content Based Filtering

---

# Power BI Dashboards

## Job Market Overview

* Tổng số việc làm
* Job mới
* Job active
* Job hết hạn

## Skill Demand

* Kỹ năng phổ biến
* Xu hướng kỹ năng

## Salary Analysis

* Phân bố lương
* So sánh thành phố

## Source Quality

* Chất lượng từng website
* Tỷ lệ lỗi crawl
* Tỷ lệ dữ liệu thiếu

---

# Airflow Pipelines

Pipeline hàng ngày:

```text
crawl_jobs
    ↓
save_raw
    ↓
load_staging
    ↓
data_cleaning
    ↓
deduplication
    ↓
update_job_lifecycle
    ↓
load_silver
    ↓
load_dwh
    ↓
build_data_marts
    ↓
data_quality_checks
```

---

# Deployment

Toàn bộ hệ thống được container hóa và chạy qua Docker Compose.

Các service chính:
* `postgres`: Cơ sở dữ liệu lưu trữ metadata của Airflow.
* `floci`: Giả lập local AWS Cloud (S3) để lưu trữ các tầng Data Lake (Bronze, Silver, Gold).
* `airflow-init`: Khởi tạo môi trường, migrate db và tạo tài khoản admin cho Airflow.
* `airflow`: Chạy dịch vụ Airflow dạng Standalone (Webserver, Scheduler, Triggerer, Executor trong cùng một service gọn nhẹ).

---

# Môi trường phát triển trên WSL 2 (Windows Subsystem for Linux)

Dự án được tối ưu hóa hoàn toàn để chạy trên môi trường **WSL 2 (Ubuntu)** kết hợp với Docker. Dưới đây là hướng dẫn cài đặt và thiết lập môi trường:

## 1. Yêu cầu hệ thống
* Windows 10/11 có bật **WSL 2** (Ubuntu 20.04 hoặc 22.04+).
* Cài đặt **Docker Desktop** trên Windows và kích hoạt tích hợp **WSL 2 Integration** (trong Settings > Resources > WSL Integration > Chọn bản Ubuntu của bạn).

## 2. Thiết lập phân quyền (Permissions) trên WSL
Airflow Docker yêu cầu đồng bộ user ID để không gặp lỗi phân quyền khi ghi file log và data vào thư mục local được mount.
Trong terminal WSL, chạy lệnh sau ở thư mục gốc của dự án để ghi user ID hiện tại vào file `.env`:
```bash
echo -e "AIRFLOW_UID=$(id -u)" >> .env
```

## 3. Khởi tạo môi trường Python local
Để viết code, debug dags và dbt model ngay trên WSL:
```bash
# Tạo môi trường ảo
python3 -m venv .venv
source .venv/bin/activate

# Cài đặt thư viện dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Chạy hệ thống qua Docker Compose
Khởi động toàn bộ cụm dịch vụ:
```bash
docker compose up -d
```
Kiểm tra trạng thái các container:
```bash
docker compose ps
```

## 5. Truy cập các dịch vụ từ Windows
Nhờ tính năng localhost port forwarding tự động của WSL 2, bạn có thể truy cập các đường dẫn sau trực tiếp từ trình duyệt trên Windows:
* **Airflow Webserver UI:** [http://localhost:8080](http://localhost:8080) (Tài khoản: `admin` / Mật khẩu: `admin`)
* **Floci AWS Mock API:** `http://localhost:4566`
* **Local Postgres:** `localhost:5432`

## 6. Kiểm tra AWS S3 giả lập trên Floci
Cài đặt `awscli-local` hoặc `awscli` trên WSL để tương tác trực tiếp với Floci S3:
```bash
# Cấu hình awscli dummy credentials
aws configure set aws_access_key_id test
aws configure set aws_secret_access_key test
aws configure set default.region us-east-1

# Liệt kê các bucket đang có trên Floci
aws --endpoint-url=http://localhost:4566 s3 ls
```

---

# Project Structure


```text
job-it-data-platform/
│
├── src/
├── dags/
├── sql/
├── docs/
├── tests/
├── docker/
├── configs/
├── logs/
├── data/
└── notebooks/
```

Chi tiết được mô tả trong tài liệu Project Structure.

---

# Future Improvements

* Embedding Search
* Vector Database
* Semantic Search
* LLM-based Job Matching
* Real-time Streaming
* Multi-country Expansion
* Company Analytics
* Candidate Analytics

---

# Learning Objectives

Sau khi hoàn thành dự án, người thực hiện có thể thực hành:

* Web Crawling
* Data Modeling
* Database Design
* Data Quality
* ETL / ELT
* Incremental Load
* CDC
* SCD Type 2
* Airflow
* Docker
* Data Warehouse
* Data Mart
* Search System
* Recommendation System
* Monitoring
* Production-style Data Engineering

---

# License

This project is intended for educational and portfolio purposes.
Please respect each job website's Terms of Service and robots.txt policies when collecting data.
