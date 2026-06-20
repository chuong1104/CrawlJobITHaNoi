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
Web Crawlers
      │
      ▼
Raw Data Lake (S3 / MinIO)
      │
      ▼
Raw Layer
      │
      ▼
Staging Layer
      │
      ▼
Silver Layer (3NF Database)
      │
      ▼
Data Warehouse (Star Schema)
      │
      ▼
Data Mart
      │
      ├── Power BI
      ├── Search API
      ├── Recommendation API
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

## Storage

* PostgreSQL
* MinIO

## Data Processing

* SQL
* Python
* Pandas

## Data Warehouse

* PostgreSQL

## Orchestration

* Apache Airflow

## Containerization

* Docker
* Docker Compose

## Cloud Simulation

* Floci

## API

* FastAPI

## Dashboard

* Power BI

## Search

* PostgreSQL Full Text Search

## Monitoring

* Airflow Logs
* PostgreSQL Monitoring
* Custom Pipeline Metrics

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

Toàn bộ hệ thống chạy bằng Docker Compose.

Các service:

```text
postgres
minio
airflow-webserver
airflow-scheduler
airflow-worker
fastapi
crawler
```

Có thể triển khai trên:

* Local
* VPS
* Floci

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
