# 14. Project Structure

## 1. Mục tiêu

Mục tiêu của cấu trúc thư mục:

* Dễ mở rộng khi thêm website tuyển dụng mới.
* Dễ bảo trì khi số lượng pipeline tăng lên.
* Tách biệt crawler, ETL, warehouse và serving layer.
* Hỗ trợ Docker.
* Hỗ trợ Airflow.
* Hỗ trợ CI/CD sau này.
* Giống với cấu trúc Data Platform thực tế.

Nguyên tắc:

```text
Một thư mục = một trách nhiệm.
```

Không trộn:

```text
Crawler
SQL
API
Dashboard
```

vào cùng một nơi.

---

# 2. Cấu trúc tổng thể

```text
job-it-data-platform/

├── airflow/
├── configs/
├── data/
├── docker/
├── docs/
├── logs/
├── notebooks/
├── scripts/
├── sql/
├── src/
├── tests/
├── .env
├── .gitignore
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

# 3. Thư mục airflow

```text
airflow/

├── dags/
├── plugins/
├── logs/
└── config/
```

---

## dags

```text
airflow/dags/

├── daily_job_pipeline.py
├── weekly_maintenance.py
├── monthly_cleanup.py
├── search_reindex.py
└── recommendation_refresh.py
```

Mỗi file là một DAG.

Không viết toàn bộ logic ETL trong DAG.

DAG chỉ gọi service.

Ví dụ:

```python
PythonOperator(
    python_callable=run_silver_pipeline
)
```

---

## plugins

```text
airflow/plugins/

├── operators/
├── hooks/
└── sensors/
```

Chứa custom component.

Ví dụ:

```text
PostgresBulkLoadOperator
S3FileSensor
```

---

# 4. Thư mục configs

```text
configs/

├── crawler/
├── database/
├── logging/
├── airflow/
└── app/
```

---

Ví dụ:

```text
configs/crawler/topcv.yaml
configs/crawler/itviec.yaml
configs/crawler/jobsgo.yaml
```

---

Ví dụ:

```yaml
source_name: topcv

base_url: https://www.topcv.vn

request_delay: 2

max_retries: 3

headless: true
```

---

# 5. Thư mục data

```text
data/

├── raw/
├── staging/
├── silver/
├── gold/
└── exports/
```

Chỉ dùng cho local development.

Production sẽ dùng:

```text
S3
MinIO
Floci S3
```

---

## raw

```text
data/raw/

├── topcv/
├── itviec/
├── jobsgo/
└── ...
```

Chứa:

```text
html
json
response
```

---

## staging

```text
data/staging/
```

Dữ liệu đã parse.

---

## silver

```text
data/silver/
```

Dữ liệu sạch.

---

## gold

```text
data/gold/
```

Dataset phục vụ BI.

---

# 6. Thư mục docker

```text
docker/

├── airflow/
├── postgres/
├── minio/
├── fastapi/
└── nginx/
```

---

Ví dụ:

```text
docker/postgres/init.sql
```

Khởi tạo database.

---

Ví dụ:

```text
docker/airflow/Dockerfile
```

Image Airflow.

---

# 7. Thư mục docs

```text
docs/

├── 01_business_problem.md
├── 02_system_architecture.md
├── ...
└── 15_future_improvements.md
```

Toàn bộ tài liệu dự án.

---

# 8. Thư mục logs

```text
logs/

├── crawler/
├── pipeline/
├── airflow/
└── api/
```

---

Ví dụ:

```text
logs/crawler/topcv.log
logs/crawler/itviec.log
```

---

# 9. Thư mục notebooks

```text
notebooks/

├── exploration/
├── quality/
├── recommendation/
└── experiments/
```

---

Mục đích:

```text
EDA
Prototype
Experiment
```

Không dùng notebook cho production.

---

# 10. Thư mục scripts

```text
scripts/

├── setup/
├── migrations/
├── maintenance/
└── deployment/
```

---

Ví dụ:

```text
create_schemas.py
seed_sources.py
vacuum_database.py
```

---

# 11. Thư mục sql

```text
sql/

├── ddl/
├── dml/
├── dwh/
├── marts/
├── quality/
└── indexes/
```

---

# 12. SQL DDL

```text
sql/ddl/

├── create_sources.sql
├── create_companies.sql
├── create_jobs.sql
├── create_job_snapshots.sql
├── create_skills.sql
└── ...
```

---

# 13. SQL DWH

```text
sql/dwh/

├── create_dimensions.sql
├── create_facts.sql
├── load_dimensions.sql
└── load_facts.sql
```

---

# 14. SQL Data Mart

```text
sql/marts/

├── create_bi_marts.sql
├── create_search_mart.sql
├── create_recommendation_mart.sql
└── refresh_marts.sql
```

---

# 15. SQL Quality Checks

```text
sql/quality/

├── duplicate_jobs.sql
├── missing_salary.sql
├── invalid_experience.sql
└── null_title.sql
```

---

# 16. Thư mục src

Đây là phần quan trọng nhất.

```text
src/

├── common/
├── crawler/
├── ingestion/
├── staging/
├── silver/
├── warehouse/
├── marts/
├── search/
├── recommendation/
├── api/
└── monitoring/
```

---

# 17. common

Chứa code dùng chung.

```text
src/common/

├── config.py
├── constants.py
├── logger.py
├── hashing.py
├── text_utils.py
├── db.py
├── s3.py
└── exceptions.py
```

---

## Vai trò

Ví dụ:

```python
from src.common.db import get_db
```

Tái sử dụng toàn dự án.

---

# 18. crawler

```text
src/crawler/

├── base/
├── topcv/
├── itviec/
├── jobsgo/
├── topdev/
├── glints/
└── ...
```

---

# 19. Base Crawler

Đây là phần rất quan trọng.

```text
src/crawler/base/

├── base_crawler.py
├── base_playwright_crawler.py
├── base_scrapy_spider.py
└── request_manager.py
```

---

## base_crawler.py

Mọi crawler kế thừa.

```python
class BaseCrawler:
    pass
```

Chứa:

```text
retry
logging
headers
save raw
metrics
```

---

Ví dụ:

```python
class TopCVCrawler(BaseCrawler):
    pass
```

---

# 20. Ingestion Layer

```text
src/ingestion/

├── raw_loader.py
├── raw_validator.py
├── crawl_metadata.py
└── source_registry.py
```

---

Mục tiêu:

```text
Crawler
↓
Raw Table
```

---

# 21. Staging Layer

```text
src/staging/

├── parsers/
├── normalizers/
├── mappers/
└── loaders/
```

---

Ví dụ:

```text
salary_parser.py
experience_parser.py
location_parser.py
```

---

# 22. Silver Layer

```text
src/silver/

├── deduplication/
├── cdc/
├── scd/
├── lifecycle/
└── loaders/
```

---

Đây là nơi xử lý:

```text
duplicate jobs
job expiration
job changes
SCD Type 2
```

---

# 23. Warehouse Layer

```text
src/warehouse/

├── dimensions/
├── facts/
├── loaders/
└── sql/
```

---

Ví dụ:

```text
dim_company_loader.py
dim_skill_loader.py
fact_job_posting_loader.py
```

---

# 24. Data Mart Layer

```text
src/marts/

├── bi/
├── search/
├── recommendation/
└── refresh/
```

---

Ví dụ:

```text
build_skill_demand_mart.py
build_salary_mart.py
```

---

# 25. Search Service

```text
src/search/

├── indexing/
├── ranking/
├── query/
└── api/
```

---

Ví dụ:

```text
etl
```

sẽ map sang:

```text
Data Engineer
Data Analyst
ETL Developer
BI Engineer
```

---

# 26. Recommendation Service

```text
src/recommendation/

├── feature_store/
├── retrieval/
├── ranking/
└── training/
```

---

Ban đầu:

```text
Rule Based
```

Sau đó:

```text
Embedding
Hybrid Search
```

---

# 27. API Layer

```text
src/api/

├── routers/
├── schemas/
├── services/
├── repositories/
└── main.py
```

---

Ví dụ:

```text
GET /jobs
GET /search
GET /recommendations
```

---

# 28. Monitoring Layer

```text
src/monitoring/

├── metrics.py
├── alerts.py
├── healthcheck.py
└── dashboards.py
```

---

Theo dõi:

```text
crawl success rate
duplicates
pipeline runtime
```

---

# 29. Tests

```text
tests/

├── unit/
├── integration/
├── e2e/
└── fixtures/
```

---

## Unit Tests

```text
salary parser
experience parser
hashing
normalization
```

---

## Integration Tests

```text
crawler → raw

raw → silver

silver → warehouse
```

---

## E2E

```text
crawl

↓

warehouse

↓

search

↓

API
```

---

# 30. Environment Variables

```text
.env
```

Ví dụ:

```env
POSTGRES_HOST=postgres

POSTGRES_PORT=5432

POSTGRES_DB=job_platform

POSTGRES_USER=admin

POSTGRES_PASSWORD=password

MINIO_ENDPOINT=minio:9000

MINIO_ACCESS_KEY=minio

MINIO_SECRET_KEY=minio123
```

---

# 31. Docker Compose

```text
docker-compose.yml
```

Triển khai:

```text
Airflow
PostgreSQL
MinIO
FastAPI
Redis
```

---

# 32. Cấu trúc cuối cùng

```text
job-it-data-platform/

├── airflow/
├── configs/
├── data/
├── docker/
├── docs/
├── logs/
├── notebooks/
├── scripts/
├── sql/
├── src/
│
│   ├── common/
│   ├── crawler/
│   ├── ingestion/
│   ├── staging/
│   ├── silver/
│   ├── warehouse/
│   ├── marts/
│   ├── search/
│   ├── recommendation/
│   ├── api/
│   └── monitoring/
│
├── tests/
├── .env
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

# 33. Kiến trúc thư mục theo luồng dữ liệu

```text
crawler
    ↓

ingestion
    ↓

staging
    ↓

silver
    ↓

warehouse
    ↓

marts
    ↓

search
recommendation
BI
web app
```

Đây là cấu trúc đủ lớn để mô phỏng một Data Platform thực tế nhưng vẫn có thể triển khai hoàn toàn trên máy cá nhân bằng Docker, Airflow, PostgreSQL và MinIO/Floci.
