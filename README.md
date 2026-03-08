# Job Scraper DE Project

Hệ thống cào dữ liệu việc làm từ các trang tuyển dụng Việt Nam, xây dựng theo kiến trúc **ETL Pipeline** với **Apache Airflow** làm orchestrator.

---

## Các nguồn dữ liệu

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
| Ybox | ybox.vn | Thấp | Scrapling HTTP |
| JobStreet | jobstreet.vn | **Rất mạnh** | Playwright + Stealth |
| LinkedIn | linkedin.com | **Cực mạnh** | Playwright + Proxy |

---

## Kiến trúc Pipeline

```
[Airflow DAG: etl_job_portals_dag]
        |
        ├── [Extract] ScrapeOperator x N portals
        │       └── BaseScraper (retry, proxy, rate-limit)
        │               └── Scrapling / Playwright
        |
        ├── [Transform]
        │       ├── Cleaner    (strip HTML, parse dates)
        │       ├── Normalizer (salary, level, job_type)
        │       └── Pydantic Schema validation
        |
        └── [Load]
                └── Upsert vào PostgreSQL (INSERT ON CONFLICT)
```

---

## Khởi động nhanh

### 1. Cấu hình môi trường
```bash
cp .env.example .env
# Chỉnh sửa .env với thông tin DB và proxy của bạn
```

### 2. Build và khởi chạy
```bash
docker-compose up --build -d
```

### 3. Truy cập Airflow UI
```
http://localhost:8080
Username: admin / Password: admin
```

### 4. Chạy pipeline thủ công
Kích hoạt DAG `etl_job_portals` trong Airflow UI.

---

## Cấu trúc thư mục

```
job_scraper_de_project/
├── dags/               # Airflow DAGs & SQL scripts
├── plugins/            # Custom Operators & Hooks
├── src/
│   ├── extract/        # Scrapers cho từng portal
│   ├── transform/      # Cleaner, Normalizer, Schemas
│   └── load/           # DB connection & Upsert logic
├── data/               # Raw & Processed data (local dev)
├── tests/              # Unit tests
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Chạy tests

```bash
pytest tests/ -v
```
