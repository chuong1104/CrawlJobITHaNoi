# 09. Airflow Orchestration

## 1. Mục tiêu

Hệ thống cần tự động:

* Thu thập dữ liệu việc làm từ nhiều website tuyển dụng.
* Làm sạch và chuẩn hóa dữ liệu.
* Đồng bộ dữ liệu vào cơ sở dữ liệu 3NF.
* Thực hiện CDC, SCD và Incremental Load.
* Nạp dữ liệu vào Data Warehouse.
* Xây dựng Data Mart.
* Cập nhật Search Engine.
* Cập nhật Recommendation Engine.
* Chạy Data Quality Check.
* Gửi cảnh báo khi pipeline gặp lỗi.

Toàn bộ các tác vụ trên được điều phối bởi Apache Airflow.

---

# 2. Vai trò của Airflow trong hệ thống

Airflow không thực hiện ETL.

Airflow chỉ chịu trách nhiệm:

* Scheduling
* Orchestration
* Monitoring
* Retry
* Dependency Management
* Alerting

Ví dụ:

```text
Airflow
   |
   +--> crawl_topcv.py
   +--> crawl_itviec.py
   +--> normalize_jobs.py
   +--> load_silver.py
   +--> build_dwh.py
```

Các script ETL nằm trong source code.

Airflow chỉ gọi chúng theo đúng thứ tự.

---

# 3. Nguyên tắc thiết kế DAG

Thiết kế DAG theo nguyên tắc:

```text
Một DAG
=
Một business workflow hoàn chỉnh
```

Không nên:

```text
crawl DAG
etl DAG
warehouse DAG
mart DAG
```

vì việc debug khó khăn.

Nên:

```text
daily_job_pipeline DAG
```

bao gồm toàn bộ quy trình.

---

# 4. Kiến trúc DAG tổng thể

```text
daily_job_pipeline

├── start
│
├── crawl_sources
│   ├── topcv
│   ├── itviec
│   ├── topdev
│   ├── jobsgo
│   ├── ybox
│   ├── glints
│   └── ...
│
├── validate_raw_data
│
├── raw_to_staging
│
├── staging_to_silver
│
├── detect_duplicates
│
├── detect_job_changes
│
├── apply_scd_type2
│
├── expire_old_jobs
│
├── load_dimensions
│
├── load_fact_jobs
│
├── build_search_mart
│
├── build_recommendation_mart
│
├── build_bi_marts
│
├── run_data_quality
│
├── generate_metrics
│
├── notify_success
│
└── end
```

---

# 5. Airflow Deployment Architecture

```text
Docker Compose

├── airflow-webserver
├── airflow-scheduler
├── airflow-worker
├── airflow-triggerer
├── postgres-airflow
├── redis
└── flower
```

Project Infrastructure:

```text
Docker

├── Airflow
├── PostgreSQL (Airflow metadata)
├── Floci S3 (Data Lake: Bronze, Silver, Gold)
├── FastAPI
├── Search Service
└── Recommendation Service
```

---

# 6. DAG Schedule

## Crawl

```text
Every day
06:00
```

Ví dụ:

```python
schedule="0 6 * * *"
```

---

## Data Warehouse Refresh

```text
07:00
```

Sau khi crawl hoàn tất.

---

## Search Index Refresh

```text
07:30
```

---

## Recommendation Refresh

```text
08:00
```

---

# 7. DAG 1 - Daily Job Pipeline

Đây là DAG quan trọng nhất.

## Luồng xử lý

```text
Crawl
 ↓
Raw Validation
 ↓
Staging
 ↓
Silver
 ↓
Dedup
 ↓
SCD
 ↓
Warehouse
 ↓
Data Mart
 ↓
Quality Check
```

---

## Task Dependency

```text
start

↓

crawl_all_sources

↓

validate_raw_data

↓

raw_to_staging

↓

staging_to_silver

↓

detect_duplicates

↓

detect_changes

↓

apply_scd

↓

expire_jobs

↓

load_dimensions

↓

load_fact_jobs

↓

build_data_marts

↓

quality_checks

↓

end
```

---

# 8. Crawl Task Group

Airflow Task Group:

```text
crawl_sources

├── crawl_topcv
├── crawl_itviec
├── crawl_topdev
├── crawl_jobsgo
├── crawl_vietnamworks
├── crawl_glints
├── crawl_ybox
└── crawl_careerlink
```

Các task chạy song song.

```python
TaskGroup
```

Giúp giảm thời gian crawl.

---

# 9. Retry Strategy

Website tuyển dụng thường:

```text
429 Too Many Requests
403 Forbidden
Timeout
Cloudflare
```

Retry:

```python
retries=3
retry_delay=timedelta(minutes=5)
```

---

Ví dụ:

```python
default_args = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=5)
}
```

---

# 10. Timeout Strategy

Một crawler bị treo không được làm kẹt DAG.

Ví dụ:

```python
execution_timeout=timedelta(minutes=30)
```

Nếu quá thời gian:

```text
FAILED
```

Airflow tự retry.

---

# 11. Incremental Crawling

Không crawl toàn bộ website mỗi ngày.

Chỉ crawl:

```text
new jobs
updated jobs
recent jobs
```

Airflow truyền:

```python
crawl_date
```

vào crawler.

Ví dụ:

```text
today - 3 days
```

---

# 12. CDC Detection

Task:

```text
detect_changes
```

Mục tiêu:

```text
Job Title Changed
Salary Changed
Skill Changed
Requirement Changed
```

So sánh:

```text
latest_snapshot
vs
new_snapshot
```

bằng:

```text
content_hash
```

---

## Ví dụ

```text
Hash cũ
8f3a...

Hash mới
71ac...
```

=> tạo snapshot mới.

---

# 13. SCD Type 2

Task:

```text
apply_scd_type2
```

Thực hiện:

```text
snapshot cũ

is_current = false
valid_to = now()
```

Tạo:

```text
snapshot mới

is_current = true
valid_from = now()
```

---

# 14. Job Expiration Logic

Task:

```text
expire_old_jobs
```

Nếu:

```text
crawl thành công
nhưng không tìm thấy job
```

thì:

```text
not_found_count += 1
```

---

Ví dụ:

```text
3 lần liên tiếp không thấy
```

=> job chuyển:

```text
EXPIRED
```

---

# 15. Load Data Warehouse

Task:

```text
load_dimensions
```

Bao gồm:

```text
dim_company
dim_skill
dim_location
dim_source
dim_date
```

---

Tiếp theo:

```text
load_fact_jobs
```

Tạo:

```text
fact_job_posting
```

---

# 16. Build Data Mart

Task:

```text
build_bi_marts
```

Tạo:

```text
mart.bi_job_overview
mart.bi_skill_demand
mart.bi_salary_analysis
```

---

Task:

```text
build_search_mart
```

Tạo:

```text
mart.search_job_documents
```

---

Task:

```text
build_recommendation_mart
```

Tạo:

```text
mart.recommendation_job_features
```

---

# 17. Data Quality Check

Task:

```text
run_data_quality
```

Kiểm tra:

```text
NULL title
NULL company
Duplicate URL
Duplicate Identity Hash
Salary Outlier
Invalid Experience
```

---

Ví dụ:

```sql
SELECT COUNT(*)
FROM jobs
WHERE canonical_url IS NULL;
```

---

Nếu vượt ngưỡng:

```text
FAILED
```

DAG dừng.

---

# 18. Monitoring Metrics

Task:

```text
generate_metrics
```

Sinh metrics:

```text
Jobs Crawled
Jobs Inserted
Jobs Updated
Jobs Expired
Duplicate Jobs
Failed Pages
Runtime
```

Lưu vào:

```text
pipeline_metrics
```

---

# 19. Alerting

Airflow gửi cảnh báo:

```text
Email
Slack
Discord
Telegram
```

Ví dụ:

```text
DAG Failed
Crawler Failed
Data Quality Failed
Warehouse Load Failed
```

---

# 20. DAG Folder Structure

```text
airflow/

├── dags/
│   ├── daily_job_pipeline.py
│   ├── weekly_maintenance.py
│   └── monthly_cleanup.py
│
├── plugins/
│
├── logs/
│
└── config/
```

---

# 21. Maintenance DAG

## Weekly Maintenance

```text
weekly_maintenance
```

Nhiệm vụ:

```text
VACUUM
ANALYZE
Reindex
Cleanup Temp Tables
```

---

## Monthly Cleanup

```text
monthly_cleanup
```

Nhiệm vụ:

```text
Archive Logs
Archive Raw Files
Delete Old Crawl Artifacts
```

---

# 22. Docker Execution Flow

```text
Airflow Scheduler

↓

Trigger DAG

↓

Crawler Containers

↓

Raw Data

↓

PostgreSQL

↓

ETL

↓

Warehouse

↓

Data Mart

↓

Search API

↓

Web App

↓

PowerBI
```

---

# 23. Production-Like Architecture

```text
                    Airflow
                       |
      ----------------------------------
      |                |               |
      v                v               v

   Crawlers       ETL Jobs       DQ Checks

      |                |               |
      ----------------------------------
                       |
                       v

               PostgreSQL

        raw → staging → silver

                       |
                       v

               Data Warehouse

                       |
                       v

                  Data Mart

         --------------------------
         |            |           |
         v            v           v

      PowerBI      Search     Web App
```

---

# 24. Các DAG cuối cùng của dự án

```text
daily_job_pipeline
weekly_maintenance
monthly_cleanup
search_reindex
recommendation_refresh
```

Trong đó:

```text
daily_job_pipeline
```

là DAG trung tâm và xử lý gần như toàn bộ luồng dữ liệu của hệ thống.

---

# 25. Kết luận

Apache Airflow đóng vai trò orchestration layer của toàn bộ nền tảng dữ liệu việc làm.

Airflow không chứa logic ETL phức tạp mà chỉ điều phối:

* Crawling
* Data Validation
* CDC
* SCD Type 2
* Incremental Load
* Data Warehouse Loading
* Data Mart Building
* Search Index Refresh
* Recommendation Refresh
* Monitoring
* Alerting

Thiết kế này đủ gần với một hệ thống Data Platform thực tế và phù hợp để triển khai hoàn toàn bằng Docker trên máy cá nhân hoặc môi trường giả lập AWS thông qua Floci.
