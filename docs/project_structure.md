# Cấu Trúc Thư Mục Dự Án JobITVN (Medallion Lakehouse)

Tài liệu này giải thích chi tiết chức năng của từng thư mục, mục đích sử dụng và nhiệm vụ của các module con bên trong dự án **JobITVN Data Platform**.

---

## 📁 Tổng Quan Cấu Trúc Dự Án

```text
job_scraper_de_project/
├── .env.example               # Template biến môi trường
├── .dockerignore              # Bỏ qua các tệp không cần thiết khi build Docker
├── .gitignore                 # Loại trừ secrets, logs, local data
├── Dockerfile                 # Đóng gói image cho Airflow và scrapers
├── docker-compose.yml         # Khởi chạy Postgres 17, Floci S3, Airflow 2.10, Web API
├── requirements.txt           # Thư viện Python phụ thuộc
├── vercel.json                # Cấu hình triển khai FastAPI lên Vercel Serverless
├── README.md                  # Tài liệu tổng quan dự án chuẩn Enterprise
│
├── api/                       # Vercel Serverless Function entrypoint
│   ├── index.py               # Expose FastAPI app từ src.api.main
│   └── requirements.txt
│
├── dags/                      # Airflow DAGs (Điều phối luồng dữ liệu tự động)
│   └── daily_pipeline.py      # DAG chạy hàng ngày lúc 6:00 AM (Medallion ELT)
│
├── data/                      # Dữ liệu đệm và storage local (KHÔNG commit)
│   ├── auth/                  # Cookies/Sessions (linkedin_session.json)
│   ├── bronze/                # Raw JSON đệm từ scrapers theo source
│   ├── floci/                 # Persistent storage của AWS S3 mock
│   ├── mart_bi/               # Parquet fallback cho Power BI
│   ├── mart_ml/               # Parquet fallback cho Machine Learning
│   └── jobitvn.duckdb         # File DuckDB OLAP database chính
│
├── dbt_jobitvn/               # dbt-core Project (Data Transformation)
│   ├── models/
│   │   ├── staging/           # 8 view models làm sạch dữ liệu từ 8 nguồn
│   │   ├── intermediate/      # 5 table models union, dedup, explode skills
│   │   ├── metrics/           # dbt Semantic Layer (sem_job_market.yml)
│   │   └── marts/
│   │       ├── warehouse/     # Kimball Star Schema (fct_job_posting, dim_*)
│   │       └── mart_bi/       # 10 Aggregate models cho Power BI & API
│   ├── seeds/                 # Dữ liệu mapping tĩnh: dim_skill, dim_location
│   ├── macros/                # Macro Jinja tái sử dụng (parse_salary, parse_experience)
│   ├── tests/                 # Singular & generic data quality tests
│   ├── dbt_project.yml        # Cấu hình dự án dbt
│   └── profiles.yml           # Kết nối DuckDB / PostgreSQL
│
├── docs/                      # Tài liệu thiết kế kiến trúc hoàn chỉnh
│   ├── data_contracts/        # Pydantic & YAML Data Contracts (Bronze, Silver, Gold)
│   └── *.md                   # 20+ tài liệu chuyên sâu theo số thứ tự
│
├── logs/                      # Nhật ký hoạt động của Airflow và scrapers
├── plugins/                   # Custom plugins cho Apache Airflow
│
├── scripts/                   # Scripts vận hành độc lập & Migration SQL
│   ├── sql/                   # DDL SQL scripts
│   │   ├── silver/            # Schema Silver, CDC watermarks, Procedures, Batch procs
│   │   ├── gold/              # Schema DWH, Stored Procedures, Materialized Views
│   │   └── migrations/        # Các bản cập nhật thủ tục phòng thủ (defensive checks)
│   ├── run_scrapers.py        # CLI chạy scraper song song đa luồng ngoài Airflow
│   ├── login_linkedin_interactive.py  # Đăng nhập LinkedIn lưu session cookie
│   ├── sync_data_to_s3_parquet.py     # Đồng bộ dữ liệu local lên S3 Floci
│   ├── run_all_scrapers.sh    # Script shell test toàn bộ scrapers qua Docker
│   └── run_test_topcv.sh      # Script shell test nhanh TopCV
│
├── src/                       # Mã nguồn cốt lõi (Core Python Modules)
│   ├── config.py              # Cấu hình tập trung (paths, DB, S3, proxies)
│   ├── utils.py               # Hàm tiện ích chung (hashing, text cleaning)
│   ├── api/                   # Web Portal & REST API
│   │   ├── database.py        # Quản lý asyncpg connection
│   │   ├── main.py            # FastAPI app: QueuePool, TTL Cache, Static mount
│   │   ├── routers/jobs.py    # Router xử lý tìm kiếm và thống kê
│   │   └── static/            # Frontend Dark Mode (index.html, styles.css, app.js)
│   ├── aws/                   # Client kết nối Floci S3 (boto3 wrapper)
│   ├── extract/               # Bộ thu thập dữ liệu (Scrapling HTTP + Playwright)
│   │   ├── base_scraper.py    # Abstract base scraper (retry, rate limit, Pydantic)
│   │   ├── utils/             # Regex extractors, date parsers, string cleaners
│   │   ├── careerviet.py      # Scraper CareerViet
│   │   ├── itviec.py          # Scraper ITViec
│   │   ├── job_123.py         # Scraper 123Job
│   │   ├── joboko.py          # Scraper JobOko
│   │   ├── jobsgo.py          # Scraper JobsGO
│   │   ├── linkedin.py        # Scraper LinkedIn (Persistent Cookie Session)
│   │   ├── topcv.py           # Scraper TopCV (TLS/JA4 bypass)
│   │   └── vietnamworks.py    # Scraper VietnamWorks
│   ├── storage/               # Quản lý Data Lake & Delta Lake
│   │   ├── bronze_manager.py  # Ghi Delta Bronze, validate schema Pydantic
│   │   ├── delta_manager.py   # Wrapper deltalake: ACID, VACUUM, OPTIMIZE
│   │   └── s3_client.py       # Wrapper S3 Floci với retry logic
│   ├── schema/                # Pydantic v2 Strict Data Contracts (bronze, silver, gold)
│   ├── silver/                # Xử lý tầng Silver 3NF
│   │   ├── sync_engine.py     # Nạp DuckDB vào Postgres, chống N+1, cập nhật SCD
│   │   ├── cdc_tracker.py     # Tracking mốc watermark (last_sync_at), anomaly detection
│   │   ├── dedup_engine.py    # Khử trùng lặp cross-source bằng TF-IDF cosine similarity
│   │   └── quality_checks.py  # Kiểm tra tính toàn vẹn dữ liệu
│   ├── gold/                  # Xử lý tầng Gold
│   │   └── gold_exporter.py   # Export PostgreSQL DWH ra Delta Tables trên S3
│   └── lifecycle/             # Quản lý vòng đời dữ liệu
│       ├── bronze_archiver.py # Gom nén JSON cũ > 30 ngày thành Parquet ZSTD
│       └── lifecycle_manager.py # Điều phối các tác vụ review và bảo trì
│
└── tests/                     # Automated Tests
    └── test_*.py              # Test suite kiểm tra từng module scraper
```

---

## 📌 Vai Trò Của Các Tầng Trong Kiến Trúc

1. **`src/extract/` (Tầng Thu thập):** Sử dụng chiến thuật đa tầng (Multi-tier Strategy). Tầng siêu nhẹ dùng Scrapling HTTP (curl_cffi) giả lập TLS/JA4 fingerprint chỉ tốn 30-50MB RAM/worker cho các nguồn như TopCV, VietnamWorks, CareerViet, JobsGO. Tầng Persistent Session dùng Playwright lưu cookie session cho LinkedIn.
2. **`src/storage/` (Tầng Lakehouse):** Đảm bảo tính ACID của Data Lake trên S3 (Floci) bằng định dạng **Delta Lake** (`python-deltalake`), hỗ trợ time-travel và tự động dọn dẹp `VACUUM`.
3. **`dbt_jobitvn/` (Tầng Chuyển đổi):** DuckDB làm việc trực tiếp với file Delta/Parquet trên S3 bằng `delta_scan()`, thực hiện các model Staging và Intermediate siêu tốc mà không cần cụm Spark nặng nề.
4. **`src/silver/` (Tầng ODS 3NF):** Lưu trữ trong PostgreSQL 17, tích hợp CDC Watermark Tracker, xử lý lịch sử trạng thái bằng SCD Type 2 (`job_snapshots`) và khử trùng lặp công ty bằng `pg_trgm`.
5. **`scripts/sql/gold/` & `src/gold/` (Tầng DWH & Marts):** Xây dựng Star Schema trong PostgreSQL (`dwh`) với Fact/Dimensions, tạo các Materialized Views phục vụ Web API (<50ms) và xuất Delta Lake Marts ra S3 cho Power BI / AI.
6. **`src/api/` & `api/` (Tầng Phục vụ):** FastAPI Backend với SQLAlchemy QueuePool và TTL Cache, đi kèm giao diện Web Dashboard Dark Mode trực quan hóa số liệu thời gian thực.
