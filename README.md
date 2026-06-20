# JobITVN: Local AWS Lakehouse Data Pipeline

Hệ thống thu thập, phân tích dữ liệu việc làm từ các trang tuyển dụng Việt Nam. Dự án được xây dựng theo kiến trúc **Local AWS Lakehouse (Modern Data Stack)** tiên tiến nhất hiện nay, giả lập hoàn hảo môi trường AWS trên Local nhưng tiêu tốn cực kỳ ít tài nguyên.

---

## 🚀 Công nghệ sử dụng (The Modern Data Stack)

| Layer | Công cụ | Vai trò |
|---|---|---|
| **Orchestration** | Apache Airflow | Điều phối toàn bộ vòng đời ETL/ELT pipeline. |
| **Data Collection** | Scrapy & Playwright | Thu thập dữ liệu tĩnh và động (JS-rendered). |
| **Local Cloud Emulator** | **Floci** | Giả lập AWS S3. Nhẹ, khởi động trong 24ms, chuẩn AWS API. |
| **Data Lake Storage** | Floci S3 | Lưu trữ toàn bộ dữ liệu (JSON, Parquet) theo mô hình Medallion (Bronze/Silver/Gold). |
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
        │       └── Crawl dữ liệu -> Đẩy file JSON/HTML gốc lên `s3://jobit-bronze` (Floci S3).
        |
        └── 2. [Transform] dbt + DuckDB 
                ├── Staging (Silver): Parse lương, xử lý kiểu dữ liệu -> Lưu Parquet vào `s3://jobit-silver`.
                ├── Intermediate: Lọc trùng lặp (Deduplication), trích xuất kỹ năng.
                └── Marts (Gold): Xây dựng Star Schema (Fact/Dim) -> Lưu Parquet vào `s3://jobit-gold`.
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
| Ybox | ybox.vn | Thấp | Scrapling HTTP |
| JobStreet | jobstreet.vn | **Rất mạnh** | Playwright + Stealth |
| LinkedIn | linkedin.com | **Cực mạnh** | Playwright + Proxy + Session Manager |

---

## ⚡ Khởi động nhanh (Local Development)

### 1. Cấu hình môi trường
```bash
cp .env.example .env
# Thiết lập thông tin cho Floci S3, dbt profile
```

### 2. Khởi chạy Services (Floci, Airflow)
```bash
docker-compose up -d
```

### 3. Tương tác với Floci S3 (AWS CLI)
```bash
export AWS_ENDPOINT_URL=http://localhost:4566
aws s3 ls
```

### 4. Chạy dbt thủ công (Biến đổi dữ liệu)
```bash
dbt run --profiles-dir ./dbt --project-dir ./dbt_jobitvn
dbt test
```

---

## 📂 Cấu trúc thư mục

```text
job_scraper_de_project/
├── dags/               # Airflow DAGs
├── dbt_jobitvn/        # Thư mục project dbt (models, tests, seeds)
├── src/
│   ├── extract/        # Scrapers (cào dữ liệu)
│   └── aws/            # Utils tương tác với Floci S3 (boto3)
├── docs/               # Tài liệu thiết kế hệ thống chi tiết
├── docker-compose.yml  # Định nghĩa Airflow, Floci,...
└── requirements.txt
```

---

## 📖 Tài liệu chi tiết
Vui lòng tham khảo thư mục `docs/` để đọc chi tiết về các quyết định thiết kế kiến trúc, tổ chức Data Lakehouse và luồng xử lý ELT.
