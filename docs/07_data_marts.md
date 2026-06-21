# Data Marts Design

## Overview

Data Mart là tầng dữ liệu phục vụ trực tiếp cho từng nhóm người dùng hoặc từng hệ thống downstream.

Nhiều dự án chỉ dừng ở Data Warehouse.

Tuy nhiên trong thực tế:

```text
Dashboard
Search Engine
Recommendation Engine
Web Application
```

không nên query trực tiếp Data Warehouse.

Thay vào đó cần xây dựng các Data Mart chuyên biệt.

---

# 1. Why Data Mart?

## Problem

Data Warehouse được thiết kế cho:

* Analytics
* Aggregation
* Historical Analysis

Ví dụ:

```sql
fact_job_posting
dim_company
dim_location
dim_skill
```

Một truy vấn dashboard có thể phải join:

```text
5-10 bảng
```

Một truy vấn search có thể phải:

```text
join skills
join companies
join locations
join snapshots
```

---

## Consequences

Nếu tất cả hệ thống cùng query DWH:

* Dashboard chậm
* Search chậm
* Recommendation chậm
* Tăng tải PostgreSQL

---

## Solution

Tạo Data Mart riêng cho từng use case.

---

# 2. Data Mart Architecture

```text
Data Warehouse
       │
       ▼

 ┌───────────────┐
 │ BI Mart       │
 └──────┬────────┘
        │
        ▼
     Power BI


 ┌───────────────┐
 │ Search Mart   │
 └──────┬────────┘
        │
        ▼
     Search API


 ┌───────────────┐
 │ Reco Mart     │
 └──────┬────────┘
        │
        ▼
 Recommendation


 ┌───────────────┐
 │ Web Mart      │
 └──────┬────────┘
        │
        ▼
    Web Portal
```

---

# 3. Mart Categories

Hệ thống gồm 4 mart chính:

```text
mart_bi
mart_search
mart_recommendation
mart_web
```

---

# 4. BI Mart

## Purpose

Phục vụ:

* Power BI
* Dashboard
* Reporting

---

## Design Principle

Pre-Aggregation.

Không để Power BI tự tính toán mọi thứ.

---

# BI Mart Tables

```text
mart_job_overview_daily
mart_skill_demand_daily
mart_salary_analysis
mart_location_analysis
mart_source_quality
```

---

# 5. mart_job_overview_daily

## Purpose

Dashboard tổng quan thị trường.

---

## Schema

```sql
CREATE TABLE mart.mart_job_overview_daily (

    report_date DATE,

    total_jobs INTEGER,

    active_jobs INTEGER,

    expired_jobs INTEGER,

    new_jobs INTEGER,

    updated_jobs INTEGER
);
```

---

## Example Dashboard

```text
Total Jobs

12,500

Active Jobs

8,900

Expired Jobs

3,100

New Jobs Today

210
```

---

# 6. mart_skill_demand_daily

## Purpose

Theo dõi nhu cầu kỹ năng.

---

## Schema

```sql
CREATE TABLE mart.mart_skill_demand_daily (

    report_date DATE,

    skill_name VARCHAR(255),

    demand_count INTEGER
);
```

---

## Example

| Skill  | Demand |
| ------ | ------ |
| SQL    | 2500   |
| Python | 2100   |
| Docker | 1800   |
| Git    | 1600   |

---

# 7. mart_salary_analysis

## Purpose

Phân tích lương.

---

## Schema

```sql
CREATE TABLE mart.mart_salary_analysis (

    report_date DATE,

    family_name VARCHAR(255),

    city VARCHAR(100),

    avg_salary NUMERIC,

    median_salary NUMERIC,

    max_salary NUMERIC
);
```

---

## Example

| Role           | Avg Salary |
| -------------- | ---------- |
| Data Engineer  | 12M        |
| Backend Intern | 10M        |
| QA Intern      | 8M         |

---

# 8. mart_location_analysis

## Purpose

Theo dõi nhu cầu tuyển dụng theo khu vực.

---

## Schema

```sql
CREATE TABLE mart.mart_location_analysis (

    report_date DATE,

    city VARCHAR(100),

    active_jobs INTEGER
);
```

---

## Example

```text
Hà Nội      3200 jobs
TP.HCM      4500 jobs
Đà Nẵng      800 jobs
```

---

# 9. mart_source_quality

## Purpose

Đánh giá chất lượng nguồn dữ liệu.

---

## Schema

```sql
CREATE TABLE mart.mart_source_quality (

    report_date DATE,

    source_name VARCHAR(100),

    jobs_collected INTEGER,

    duplicate_rate NUMERIC,

    missing_rate NUMERIC,

    crawl_success_rate NUMERIC
);
```

---

## Why Important

Giúp phát hiện:

* Website nào crawl lỗi
* Website nào nhiều duplicate
* Website nào dữ liệu kém

---

# 10. Search Mart

## Purpose

Phục vụ tìm kiếm việc làm.

---

## Why Separate?

Search cần:

* ít join
* phản hồi nhanh

---

Không nên query:

```text
jobs
companies
skills
locations
snapshots
```

mỗi lần người dùng search.

---

# Search Mart Design

Mỗi job chỉ còn:

```text
1 document
```

---

# mart_search_documents

## Schema

```sql
CREATE TABLE mart.mart_search_documents (

    job_id BIGINT PRIMARY KEY,

    title TEXT,

    company_name TEXT,

    city TEXT,

    family_name TEXT,

    salary_text TEXT,

    skill_text TEXT,

    search_document TSVECTOR,

    last_updated TIMESTAMP
);
```

---

# Example

```text
title:
Data Engineer Intern

skills:
SQL Python Airflow Docker ETL

family:
Data Engineer
```

---

# Search Index

```sql
CREATE INDEX idx_search_doc
ON mart.mart_search_documents
USING GIN(search_document);
```

---

# Search Query Example

User search:

```text
etl
```

---

Search Engine trả về:

```text
Data Engineer Intern

BI Developer Intern

Data Pipeline Intern
```

---

# 11. Recommendation Mart

## Purpose

Tăng tốc Recommendation Engine.

---

## Problem

Không nên tính recommendation trực tiếp từ DWH.

---

## Solution

Materialize toàn bộ feature.

---

# mart_recommendation_features

## Schema

```sql
CREATE TABLE mart.mart_recommendation_features (

    job_id BIGINT PRIMARY KEY,

    family_name VARCHAR(255),

    city VARCHAR(100),

    salary_min NUMERIC,

    salary_max NUMERIC,

    skill_vector JSONB,

    recommendation_vector JSONB
);
```

---

## Example

```json
{
  "python": 1,
  "sql": 1,
  "docker": 1,
  "airflow": 1
}
```

---

# Recommendation Flow

```text
User Skills
      │
      ▼

Feature Matching
      │
      ▼

Top-N Jobs
```

---

# 12. Web Serving Mart

## Purpose

Phục vụ website.

---

## Why Needed

Website chỉ cần:

```text
active jobs
```

Không cần:

* historical data
* warehouse joins

---

# mart_active_jobs

## Schema

```sql
CREATE TABLE mart.mart_active_jobs (

    job_id BIGINT PRIMARY KEY,

    title TEXT,

    company_name TEXT,

    city TEXT,

    salary_text TEXT,

    family_name TEXT,

    source_name TEXT,

    posted_date DATE,

    expired_date DATE,

    detail_url TEXT
);
```

---

## Benefits

Frontend query rất đơn giản.

---

# 13. Data Mart Refresh Strategy

## Daily Refresh

Sau khi load DWH.

---

Flow:

```text
Silver
   │
   ▼

DWH
   │
   ▼

Build Data Marts
   │
   ▼

Power BI
Search
Reco
Web
```

---

# 14. Incremental Mart Loading

Không rebuild toàn bộ mart.

---

## Logic

```text
New Job
Updated Job
Expired Job
```

mới được refresh.

---

## Benefits

* Nhanh hơn
* Ít tài nguyên hơn

---

# 15. Airflow DAG

```text
load_dwh

      │
      ▼

build_bi_marts

      │
      ├──────────────┐
      ▼              ▼

build_search_mart

build_reco_mart

      ▼
build_web_mart

      ▼
data_quality_checks
```

---

# 16. Data Freshness

Target:

```text
< 24h
```

---

Ví dụ:

Crawler chạy:

```text
01:00
```

Pipeline hoàn thành:

```text
03:00
```

Người dùng thấy dữ liệu mới nhất:

```text
03:05
```

---

# 17. Materialized Views vs Physical Tables

Có hai lựa chọn.

---

## Materialized View

Ưu điểm:

* Dễ build

Nhược điểm:

* Refresh chậm

---

## Physical Tables

Ưu điểm:

* Nhanh
* Linh hoạt

Nhược điểm:

* ETL phức tạp hơn

---

## Project Decision

Sử dụng:

```text
Physical Tables
```

---

# 18. Why Data Mart Is Important

Nếu bỏ Data Mart:

```text
Power BI
Search API
Recommendation API
Web App
```

đều truy cập DWH trực tiếp.

Kết quả:

* Query phức tạp
* Hiệu năng kém
* Khó mở rộng

---

# 19. Complete Serving Layer

```text
Data Warehouse
       │
       ▼

────────────────────

mart_job_overview_daily
mart_skill_demand_daily
mart_salary_analysis
mart_location_analysis
mart_source_quality

        │
        ▼

      Power BI

────────────────────

mart_search_documents

        │
        ▼

      Search API

────────────────────

mart_recommendation_features

        │
        ▼

 Recommendation API

────────────────────

mart_active_jobs

        │
        ▼

     Web Portal
```

---

# Summary

Data Mart là tầng cuối cùng trước khi dữ liệu được sử dụng.

Thiết kế cuối cùng gồm:

```text
BI Mart
Search Mart
Recommendation Mart
Web Mart
```

Mỗi mart được tối ưu cho một workload riêng.

Cách tiếp cận này gần với kiến trúc được sử dụng trong các hệ thống dữ liệu thực tế hơn là để tất cả ứng dụng truy cập trực tiếp vào Data Warehouse.
