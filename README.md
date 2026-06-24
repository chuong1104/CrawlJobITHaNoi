# JobITVN: Local AWS Lakehouse Data Pipeline

Hệ thống thu thập, phân tích dữ liệu việc làm từ các trang tuyển dụng Việt Nam. Dự án được xây dựng theo kiến trúc **Local AWS Lakehouse (Modern Data Stack)** tiên tiến nhất hiện nay, giả lập hoàn hảo môi trường AWS trên Local nhưng tiêu tốn cực kỳ ít tài nguyên.

---

## 🚀 Công nghệ sử dụng (The Modern Data Stack)

| Layer | Công cụ | Vai trò |
|---|---|---|
| **Orchestration** | Apache Airflow | Điều phối toàn bộ vòng đời ETL/ELT pipeline. |
| **Data Collection** | Scrapling & Playwright | Thu thập dữ liệu tĩnh và động (JS-rendered). |
| **Local Cloud Emulator** | **Floci** | Giả lập AWS S3. Nhẹ, khởi động trong 24ms, chuẩn AWS API. |
| **Data Lake Storage** | Floci S3 | Lưu trữ toàn bộ dữ liệu (JSONL, Parquet) theo mô hình Medallion (Bronze/Silver/Gold). |
| **Compute Engine** | **DuckDB** | Truy vấn và phân tích siêu tốc trực tiếp trên file Parquet từ S3. |
| **Transformation** | **dbt-core** | Xây dựng logic làm sạch, parse lương, và build Fact/Dim bằng SQL. |
| **Serving** | FastAPI & Power BI | Cung cấp dữ liệu cho ứng dụng frontend và báo cáo Dashboard. |

---

## 🏗 Kiến trúc Pipeline (ELT)

Dữ liệu di chuyển theo chuẩn **Medallion Architecture**:

```text
[Airflow DAG]
        |
        ├── 1. [Extract & Load] Scraper
        │       └── Crawl dữ liệu -> Validate (Pydantic) -> Đẩy JSONL lên `s3://jobit-bronze` (Floci S3).
        |
        └── 2. [Transform] dbt + DuckDB
                ├── Silver: Parse lương, chuẩn hoá địa điểm -> Parquet `s3://jobit-silver`.
                ├── Intermediate: Deduplication, trích xuất kỹ năng.
                └── Gold (Marts): Star Schema (Fact/Dim) -> Parquet `s3://jobit-gold`.
```

---

## 🌐 Các nguồn dữ liệu đang hỗ trợ

| Portal | URL | Anti-bot | Phương pháp |
|---|---|---|---|
| TopCV | topcv.vn | Trung bình | Scrapling HTTP |
| ITViec | itviec.com | Thấp | Scrapling HTTP |
| VietnamWorks | vietnamworks.com | Trung bình | REST API |
| JobsGO | jobsgo.vn | Thấp | Scrapling HTTP |
| Joboko | joboko.com | Thấp | Scrapling HTTP |
| 123job | 123job.vn | Trung bình | Scrapling HTTP |
| CareerViet | careerviet.vn | Trung bình | Scrapling HTTP |
| CareerLink | careerlink.vn | Thấp | Scrapling HTTP |
| LinkedIn | linkedin.com | **Cực mạnh** | Playwright + Proxy + Session Manager |

---

## ⚡ Khởi động nhanh (Local Development)

### 1. Cấu hình môi trường
Sao chép file mẫu và cấu hình các thông số cần thiết:
```bash
cp .env.example .env
```

Cấp quyền cho thư mục logs (tránh lỗi phân quyền trên Linux/macOS):
```bash
chmod -R 777 logs
```

### 2. Khởi chạy Services (Docker Compose)
```bash
docker compose up -d
```

### 3. Khởi tạo S3 Buckets trên Floci
Chạy một lần duy nhất để tạo các bucket `jobit-bronze`, `jobit-silver`, `jobit-gold`:
```bash
docker compose exec airflow env PYTHONPATH=/opt/airflow python -m src.storage.init_buckets
```

### 4. Chạy tất cả Scrapers song song
Chạy toàn bộ scraper song song với `scripts/run_scrapers.py`:

```bash
# Cào đầy đủ (lấy URL + parse chi tiết từng job)
python scripts/run_scrapers.py --mode full --workers 4

# Chỉ cào danh sách URL (nhanh hơn, dùng để test)
python scripts/run_scrapers.py --mode links --pages 2

# Xem tất cả options
python scripts/run_scrapers.py --help
```

Hoặc chạy trong Docker container:
```bash
docker compose exec airflow env PYTHONPATH=/opt/airflow \
  python /opt/airflow/scripts/run_scrapers.py --mode full --workers 4
```

### 5. Đăng nhập LinkedIn (lấy session cookie)
```bash
python scripts/login_linkedin_interactive.py
```

### 6. Tương tác với Floci S3 (AWS CLI)

- **Liệt kê dữ liệu Bronze:**
  ```bash
  aws --endpoint-url=http://localhost:4566 s3 ls s3://jobit-bronze/ --recursive
  ```

- **Xem nội dung file:**
  ```bash
  aws --endpoint-url=http://localhost:4566 s3 cp s3://jobit-bronze/valid/source=topcv/... -
  ```

### 7. Chạy dbt thủ công
```bash
dbt run --profiles-dir ./dbt --project-dir ./dbt_jobitvn
dbt test
```

---

## 📂 Cấu trúc thư mục

```text
job_scraper_de_project/
├── dags/               # Airflow DAGs
│   └── daily_pipeline.py
├── dbt_jobitvn/        # dbt project (models, tests, seeds)
├── src/
│   ├── config.py       # Cấu hình toàn cục (paths, env vars)
│   ├── utils.py        # Shared utilities
│   ├── extract/        # E - Scrapers (cào dữ liệu)
│   │   └── job_online/ # 9 scrapers: topcv, itviec, linkedin...
│   ├── storage/        # Storage layer (S3 client, BronzeManager)
│   └── schema/         # Pydantic schemas (bronze, silver, gold)
├── scripts/            # Executable scripts
│   ├── run_scrapers.py # Chạy tất cả scrapers song song
│   └── login_linkedin_interactive.py
├── tests/              # Integration & selector tests
├── data/               # Data lake local (gitignore'd)
│   ├── bronze/         # Layer 1: Raw validated
│   ├── silver/         # Layer 2: Cleaned
│   └── gold/           # Layer 3: Aggregated
├── docs/               # Tài liệu thiết kế
├── docker-compose.yml
└── requirements.txt
```

---

## 📖 Tài liệu chi tiết
Vui lòng tham khảo thư mục `docs/` để đọc chi tiết về các quyết định thiết kế kiến trúc, tổ chức Data Lakehouse và luồng xử lý ELT.
