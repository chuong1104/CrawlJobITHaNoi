# Project Structure (Medallion Lakehouse Stack)

## 1. Mục tiêu

Kiến trúc thư mục được tinh gọn và tổ chức khoa học để phục vụ mô hình **ELT (Extract, Load, Transform)** kết hợp giữa Delta Lakehouse (Floci S3) và DWH (DuckDB + PostgreSQL).

Mục tiêu cấu trúc:
* **Tách biệt Storage và Compute:** Không commit data thô lên git. Mọi dữ liệu thô và marts phân tích được quản lý bằng Delta Lake trên Floci S3.
* **Quy hoạch rõ ràng:** Phân biệt rõ code cào dữ liệu (Python/Playwright), code đồng bộ/xử lý nghiệp vụ (Python Sync/CDC Engine) và code biến đổi phân tích (dbt/SQL).
* **Quản lý Schema và Metadata:** Tích hợp các file Data Contracts và dbt Semantic Layer trực tiếp trong thư mục dự án.

---

# 2. Cấu trúc tổng thể

```text
job_scraper_de_project/
├── .env.example               # Template biến môi trường (commit được)
├── .gitignore                 # Exclude secrets, data, logs, cache
├── .dockerignore
├── Dockerfile                 # Image build cho Airflow + scrapers
├── docker-compose.yml         # Services: Postgres 17, Floci S3, Airflow 2.10, Web API
├── requirements.txt           # Thư viện Python
├── vercel.json                # Cấu hình deploy FastAPI lên Vercel
├── README.md                  # Giới thiệu & hướng dẫn nhanh
├── api/                       # Vercel Serverless Entrypoint
│   ├── index.py               # Expose FastAPI app cho Vercel runtime
│   └── requirements.txt
│
├── dags/                      # Airflow DAGs (Điều phối luồng)
│   └── daily_pipeline.py      # DAG chạy pipeline hàng ngày
│
├── dbt_jobitvn/               # dbt Project (Data Transformation)
│   ├── models/
│   │   ├── staging/           # Tầng làm sạch & chuẩn hóa (8 view models)
│   │   ├── intermediate/      # Dedup, union, logic phức tạp (5 table models)
│   │   ├── metrics/           # dbt Semantic Layer (MetricFlow)
│   │   └── marts/
│   │       ├── warehouse/     # Star Schema DWH — Kimball (fct, dim, bridge)
│   │       └── mart_bi/       # 10 Aggregate models cho Power BI & API
│   ├── seeds/                 # Dữ liệu tĩnh: dim_skill, dim_location
│   ├── macros/                # Hàm Jinja tái sử dụng
│   ├── tests/                 # Singular tests kiểm tra chất lượng dữ liệu
│   ├── dbt_project.yml        # Cấu hình dự án dbt
│   └── profiles.yml           # Cấu hình kết nối DuckDB / PostgreSQL
│
├── docs/                      # Tài liệu thiết kế hệ thống
│   ├── data_contracts/        # Data Contracts (Bronze, Silver, Gold schema)
│   └── *.md                   # Các tài liệu thiết kế theo số thứ tự
│
├── scripts/                   # Scripts vận hành & SQL DDL
│   ├── sql/                   # SQL DDL Migration scripts
│   │   ├── silver/            # Schema Silver, CDC watermarks, Procedures, Batch procs
│   │   └── gold/              # Schema DWH, Stored Procedures, Materialized Views
│   ├── run_scrapers.py        # Chạy scraper thủ công ngoài Airflow
│   ├── login_linkedin_interactive.py  # Đăng nhập LinkedIn lấy session
│   ├── sync_data_to_s3_parquet.py     # Đồng bộ local JSONL lên S3 Floci
│   ├── run_all_scrapers.sh    # Shell runner: test tất cả scrapers qua Docker
│   └── run_test_topcv.sh      # Shell runner: test TopCV qua Docker
│
├── src/                       # Mã nguồn Python
│   ├── config.py              # Cấu hình tập trung (env vars, paths)
│   ├── utils.py               # Helper functions dùng chung
│   ├── api/                   # FastAPI Web Portal
│   │   ├── database.py        # Kết nối CSDL asyncpg
│   │   ├── main.py            # App chính (SQLAlchemy QueuePool, TTL Cache, Static mount)
│   │   ├── routers/jobs.py    # Endpoints tra cứu job & stats
│   │   └── static/            # Frontend Dark Mode (index.html, styles.css, app.js)
│   ├── aws/                   # Helper kết nối AWS/Floci S3
│   ├── extract/               # Python Scrapers (Playwright/Scrapling)
│   │   ├── base_scraper.py    # Abstract base class cho mọi scraper
│   │   ├── utils/             # Tiện ích nội bộ (regex_extractor...)
│   │   ├── careerviet.py
│   │   ├── itviec.py
│   │   ├── job_123.py
│   │   ├── joboko.py
│   │   ├── jobsgo.py
│   │   ├── linkedin.py
│   │   ├── topcv.py
│   │   └── vietnamworks.py
│   ├── storage/               # Quản lý Delta Lake & Bronze Manager
│   ├── schema/                # Pydantic schemas validation
│   ├── silver/                # Sync Engine, CDC Tracker, Dedup Engine, Quality Checks
│   ├── gold/                  # GoldExporter (DWH → S3 Delta Tables)
│   └── lifecycle/             # Bronze archiver + Job lifecycle manager
│
├── data/                      # Dữ liệu local (KHÔNG commit, chỉ .gitkeep)
│   ├── bronze/                # Raw JSON từ scrapers (partitioned by source)
│   ├── silver/                # (reserved)
│   ├── gold/                  # (reserved)
│   ├── floci/                 # Floci S3 mock volume
│   ├── mart_bi/               # Export BI marts (Parquet)
│   ├── mart_ml/               # Export ML datasets (Parquet)
│   ├── auth/                  # Session cookies (KHÔNG commit)
│   └── jobitvn.duckdb         # DuckDB database chính
│
├── tests/                     # Unit & integration tests (chỉ .py)
│   └── test_*.py              # Test từng scraper
│
├── plugins/                   # Airflow custom plugins
└── logs/                      # Airflow logs (KHÔNG commit)
```

---

# 3. Chi tiết các Module quan trọng

### 3.1. `src/storage/` (Storage Layer)
* **`delta_manager.py`:** Wrapper cho `python-deltalake`. Quản lý đọc/ghi Delta Table trên S3, hỗ trợ Time Travel, và bảo trì (`VACUUM`, `OPTIMIZE`).
* **`bronze_manager.py`:** Quản lý quy trình Pydantic validation trước khi đẩy lên S3 Bronze.
* **`s3_client.py`:** Wrapper kết nối S3/Floci với retry logic.

### 3.2. `src/silver/` (Sync & CDC Layer)
* **`cdc_tracker.py`:** Quản lý watermark đồng bộ (`last_sync_at`) trong PostgreSQL, phát hiện anomaly khi scraper bị block.
* **`dedup_engine.py`:** Loại bỏ job posting trùng lặp cross-source dựa trên fuzzy matching.
* **`sync_engine.py`:** Đồng bộ dữ liệu từ DuckDB intermediate vào PostgreSQL Silver schema.
* **`quality_checks.py`:** Kiểm tra chất lượng dữ liệu trước khi load.

### 3.3. `dbt_jobitvn/models/` (Transformation Layer)

| Layer | Folder | Materialization | Mô tả |
|---|---|---|---|
| Staging | `staging/` | View | Làm sạch, rename, cast type (8 models) |
| Intermediate | `intermediate/` | Table | Union 8 nguồn (`int_all_jobs_unioned`), dedup, explode skills |
| DWH | `marts/warehouse/` | Table | Star Schema: dim_*, fct_*, bridge_* |
| BI Mart | `marts/mart_bi/` | Incremental | 10 models: KPI, trend, salary aggregates |
| Semantic | `models/metrics/` | `.yml` only | MetricFlow definitions (`sem_job_market.yml`) |

### 3.4. `dbt_jobitvn/seeds/` (Static Reference Data)
* **`dim_skill_mapping.csv`:** Chuẩn hóa tên skill (e.g. "JS" → "JavaScript").
* **`dim_location_mapping.csv`:** Chuẩn hóa tên tỉnh/thành phố.

### 3.5. `src/api/` (Serving Layer & Web Portal)
* **FastAPI Backend:** Kết nối PostgreSQL thông qua **SQLAlchemy QueuePool** (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`) giúp tái sử dụng kết nối.
* **In-Memory TTL Caching:** Decorator `ttl_cache(seconds=300)` giảm tải tối đa cho PostgreSQL Gold DWH, response time < 50ms.
* **Frontend Web Dashboard:** Static assets (`static/index.html`, `styles.css`, `app.js`) giao diện Vibrant Dark Mode phục vụ trực tiếp tại root `/`.
* **Serverless Deployment:** Entrypoint `api/index.py` và `vercel.json` hỗ trợ deploy miễn phí lên Vercel.

### 3.6. `scripts/` (Ops & Migration)
* **`scripts/sql/silver/`:** DDL tạo Silver schema, CDC watermark tables, stored procedures.
* **`scripts/sql/gold/`:** DDL tạo Gold DWH schema và Materialized Views cho API + Power BI DirectQuery.
* **`scripts/run_scrapers.py`:** CLI runner để chạy scrapers thủ công ngoài Airflow.
* **`scripts/run_all_scrapers.sh`:** Shell runner test tất cả scrapers qua Docker container.

### 3.7. `src/lifecycle/` (Lifecycle Layer)
* **`bronze_archiver.py`:** Gom nén JSON Bronze cũ > 30 ngày thành Parquet ZSTD trên S3 Archive.
* **`lifecycle_manager.py`:** Orchestrate các task lifecycle đặc biệt (manual review queue, alerts).

---

# 4. Luồng dữ liệu tổng thể

```
[Scrapers] → data/bronze/{source}/ (JSON)
    ↓ BronzeManager (Pydantic validate + S3 upload)
[Floci S3] Bronze Delta Tables
    ↓ SyncEngine + CDCTracker
[PostgreSQL] Silver schema (normalized)
    ↓ dbt run (staging → intermediate → marts)
[DuckDB / PostgreSQL] Gold DWH + BI Marts
    ↓ GoldExporter
[Floci S3] Gold Delta Tables + Power BI / FastAPI
```

---

# 5. Quy tắc `.gitignore`

| Loại file | Quy tắc |
|---|---|
| Secrets (`.env`, `*_session.json`) | Ignore hoàn toàn, chỉ commit `.env.example` |
| Data (`data/bronze/*`, etc.) | Ignore data, chỉ giữ `.gitkeep` |
| DuckDB files (`*.duckdb`) | Ignore hoàn toàn — DB nằm trong `data/` |
| Airflow local (`airflow.cfg`, `airflow.db`) | Ignore — chỉ dùng qua Docker |
| dbt artifacts (`target/`, `dbt_packages/`) | Ignore — generate lại khi chạy |
| Scratch (`scratch/`) | Ignore — chỉ dùng locally |
