# JobITVN: Local AWS Lakehouse Data Pipeline

Hệ thống thu thập, phân tích dữ liệu việc làm từ các trang tuyển dụng Việt Nam. Dự án được xây dựng theo kiến trúc **Local AWS Lakehouse (Modern Data Stack)** tiên tiến, kết hợp hoàn hảo giữa Hồ dữ liệu (Delta Lake) và Cơ sở dữ liệu nghiệp vụ quan hệ (PostgreSQL), giả lập hoàn hảo môi trường AWS trên Local nhưng tiêu tốn cực kỳ ít tài nguyên.

---

##  Công nghệ sử dụng (The Modern Data Stack v2.1)

| Layer | Công cụ | Vai trò |
|---|---|---|
| **Orchestration** | **Apache Airflow** | Lập lịch và điều phối toàn bộ vòng đời Medallion pipeline. Tự động dọn dẹp Delta Tables cũ thông qua task `VACUUM`. |
| **Data Collection** | **Scrapling & Playwright** | Thu thập dữ liệu hiệu suất cao. `Scrapling` dùng cho trang tĩnh. `Playwright` dùng cho LinkedIn với cookie session. |
| **Data Lake Storage** | **Delta Lake (S3)** | Định dạng **Delta Table** trên Floci S3 cho Bronze & Gold. Đảm bảo giao dịch ACID, tự động merge schema mới và hỗ trợ Time Travel. |
| **Operational DB (Silver)** | **PostgreSQL (3NF ODS)** | Database nghiệp vụ để chuẩn hóa dạng 3NF, xử lý SCD Type 2 lịch sử tin tuyển dụng (`job_snapshots`) và fuzzy matching tên công ty (`pg_trgm`). |
| **Compute Engine** | **DuckDB & PostgreSQL** | Cỗ máy phân tích (Analytical Engine) truy vấn song hành. DuckDB quét Delta S3 qua `delta_scan()`, PostgreSQL xử lý quan hệ và views. |
| **Transformation** | **dbt-core** | Làm sạch, trích xuất dữ liệu. Quản lý các chỉ số tập trung bằng **dbt Semantic Layer (MetricFlow)**. |
| **Serving** | **FastAPI & Power BI** | FastAPI kết nối PostgreSQL để đọc các **Materialized Views** tối ưu (<100ms). Power BI quét trực tiếp Delta tables trên S3. |

---

##  Kiến trúc Pipeline (Medallion ELT)

Dữ liệu di chuyển theo chuẩn **Medallion Architecture**, tách biệt hoàn toàn Storage (S3) và Compute (DuckDB/PostgreSQL):

```text
[Apache Airflow]
       │
       ├── 1. [EXTRACT & LOAD] Scraper Pipeline
       │       └── Crawl dữ liệu -> Pydantic Validation -> Ghi Delta Table Bronze.
       │       └── Đường dẫn: `s3://jobit-bronze/bronze/{source}/` (partition theo _batch_date).
       │
       ├── 2. [TRANSFORM] dbt (Staging)
       │       └── DuckDB đọc Delta Bronze bằng delta_scan() -> Chuẩn hóa ngày, lương, skill.
       │
       ├── 3. [SYNC & CDC] Python Sync Engine
       │       └── So khớp watermark `scraped_at > last_sync_at` để giảm 80-90% data ghi vào Silver.
       │       └── Upsert dữ liệu 3NF vào PostgreSQL Silver. Cập nhật SCD Type 2 lịch sử.
       │       └── Chạy Stored Procedures nạp Gold DWH và REFRESH các Materialized Views.
       │
       └── 4. [EXPORT & VACUUM] Gold Marts
               └── Export DWH ra Delta Tables trên S3 (`s3://jobit-gold/gold/mart_bi/`).
               └── Chạy VACUUM dọn dẹp các tệp tin log và Parquet thừa cũ hơn 7 ngày trên S3.
```

---

##  Các nguồn dữ liệu đang hỗ trợ

Hệ thống được thiết kế linh hoạt để đối phó với nhiều cấp độ bảo mật Anti-bot khác nhau:

| Nền tảng (Portal) | URL | Mức độ Anti-bot | Phương pháp Thu thập (Strategy) |
|---|---|---|---|
| **TopCV** | topcv.vn | Trung bình | `Scrapling HTTP` (Lấy HTML tĩnh trực tiếp) |
| **ITViec** | itviec.com | Thấp | `Scrapling HTTP` |
| **VietnamWorks** | vietnamworks.com | Trung bình | `REST API` (Reverse engineering API nội bộ) |
| **JobsGO** | jobsgo.vn | Thấp | `Scrapling HTTP` |
| **Joboko** | joboko.com | Thấp | `Scrapling HTTP` |
| **123job** | 123job.vn | Trung bình | `Scrapling HTTP` |
| **CareerViet** | careerviet.vn | Trung bình | `Scrapling HTTP` |
| **CareerLink** | careerlink.vn | Thấp | `Scrapling HTTP` |
| **LinkedIn** | linkedin.com | **Rất Khắc Nghiệt** | `Playwright` + Proxy + **Quản lý Session Cookie** |

---

## Hướng dẫn Cookie cho LinkedIn

LinkedIn áp dụng các biện pháp chặn bot vô cùng khắt khe. Nếu request liên tục mà không duy trì phiên đăng nhập hợp lệ, tài khoản của bạn hoặc IP sẽ bị khóa. Hệ thống giải quyết việc này bằng cách lưu trữ **Session Cookie** để mô phỏng người dùng thật.

**Cách 1: Khởi tạo cookie tự động qua Playwright UI (Khuyến nghị cho Local)**
Chạy script dưới đây. Một cửa sổ trình duyệt Chromium sẽ bật lên để bạn tự tay nhập tài khoản, mật khẩu và giải CAPTCHA (nếu có). Sau khi login thành công, hệ thống tự động trích xuất cookie và đóng trình duyệt.
```bash
python scripts/login_linkedin_interactive.py
```
> [!NOTE]
> Cookie được lưu tự động tại thư mục: `src/extract/job_online/auth/linkedin_state.json`. Thư mục này đã được thêm vào `.gitignore` để tránh rò rỉ phiên đăng nhập của bạn lên Git.

---

## Hướng dẫn Cài đặt & Chạy dự án (Docker)

Để triển khai dự án một cách đồng bộ và tránh các lỗi môi trường, chúng tôi khuyến nghị sử dụng **Docker** và **Docker Compose**. Dưới đây là hướng dẫn chi tiết từng bước:

### 1. Yêu cầu hệ thống (Prerequisites)
- Đã cài đặt [Docker](https://www.docker.com/products/docker-desktop/) và [Docker Compose](https://docs.docker.com/compose/install/).
- Đã cài đặt [Git](https://git-scm.com/).
- Cấp phát ít nhất 4GB RAM cho Docker Engine (khuyến nghị 8GB).

### 2. Clone dự án và Cấu hình môi trường
Mở terminal và chạy các lệnh sau:
```bash
# Clone repository
git clone https://github.com/chuong1104/CrawlJobITHaNoi.git
cd CrawlJobITHaNoi

# Tạo file cấu hình môi trường từ template
cp .env.example .env
```
Mở file `.env` vừa tạo để xem và chỉnh sửa (nếu cần). Các thông số mặc định đã được thiết lập sẵn để chạy local.

### 3. Phân quyền thư mục lưu trữ
Để tránh lỗi phân quyền (Permission denied) khi Airflow ghi log hoặc Floci lưu dữ liệu trên hệ điều hành Linux/macOS, hãy chạy lệnh:
```bash
mkdir -p logs data/floci
chmod -R 777 logs data
```

### 4. Build và Khởi chạy hệ thống (Docker Services)
Sử dụng Docker Compose để khởi chạy toàn bộ kiến trúc (Postgres, Floci S3, Airflow):
```bash
docker compose build
docker compose up -d
```
> [!TIP]
> **Airflow Web UI** hiện đã có thể truy cập tại: **http://localhost:8080**
> Tài khoản mặc định: `admin` / Mật khẩu: `admin`

### 5. Khởi tạo Database Migrations (CDC & Materialized Views)
Chạy các scripts SQL để tạo các bảng logic CDC, logging và Materialized Views tối ưu cho Serving API:
```bash
# Tạo bảng Silver ODS, companies, jobs, snapshots
docker compose exec airflow psql -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/01_create_silver_schema.sql

# Tạo bảng CDC Watermark và Run log (v2.1)
docker compose exec airflow psql -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/02_create_cdc_tables.sql

# Tạo Gold DWH schema
docker compose exec airflow psql -U airflow -d job_scraper_db -f /opt/airflow/scripts/gold/01_create_gold_dwh_schema.sql

# Tạo Materialized Views DWH (v2.1)
docker compose exec airflow psql -U airflow -d job_scraper_db -f /opt/airflow/scripts/gold/02_create_materialized_views.sql
```

### 6. Khởi tạo Data Lake (Delta Lake Buckets)
Chạy lệnh sau để tạo các bucket `jobit-bronze` và `jobit-gold` trên Floci S3:
```bash
docker compose exec airflow env PYTHONPATH=/opt/airflow python -m src.storage.init_buckets
```

### 7. Thực thi Crawling Dữ Liệu (Extraction)
Chạy script để kích hoạt các scrapers. Dữ liệu thô thu thập được (JSON) sẽ được validate và stream trực tiếp lên Delta Lake Bronze.
```bash
# Chạy cào toàn bộ (full) với 4 luồng song song
docker compose exec airflow env PYTHONPATH=/opt/airflow python /opt/airflow/scripts/run_scrapers.py --mode full --workers 4
```

### 8. Chạy dbt Transformation & dbt Semantic Layer
Thực thi dbt bên trong container Airflow:
```bash
# 1. Chạy dbt staging để làm sạch dữ liệu từ Delta Bronze S3
docker compose exec airflow dbt run --select staging intermediate --profiles-dir ./dbt_jobitvn --project-dir ./dbt_jobitvn

# 2. Đồng bộ vào PostgreSQL (Silver & Gold DWH & Marts) thông qua Airflow task hoặc chạy command sync thủ công:
docker compose exec airflow env PYTHONPATH=/opt/airflow python -m src.silver.sync_engine

# 3. Test các metrics với dbt Semantic Layer CLI
docker compose exec airflow dbt sl list metrics --profiles-dir ./dbt_jobitvn --project-dir ./dbt_jobitvn
```

---

## Cấu trúc thư mục chi tiết

Dự án được tổ chức theo tiêu chuẩn của một Data Platform hiện đại, chia tách rõ ràng các tầng nghiệp vụ:

```text
job_scraper_de_project/
├── dags/               # Airflow DAGs: Định nghĩa lịch trình chạy pipeline tự động (Daily/Weekly).
│   └── daily_pipeline.py
├── dbt_jobitvn/        # dbt Project: Toàn bộ logic Transform bằng SQL (Models, Metrics, Tests, Seeds).
├── src/                # Mã nguồn chính (Core Python Logic):
│   ├── config.py       # - Quản lý cấu hình toàn cục (Environment variables, Paths).
│   ├── utils.py        # - Các hàm tiện ích dùng chung (Logger, Text normalizers).
│   ├── extract/        # - Module thu thập dữ liệu bằng Playwright & Scrapling.
│   ├── storage/        # - Quản lý Delta Lake (DeltaLakeManager) thông qua python-deltalake.
│   ├── schema/         # - Định nghĩa cấu trúc dữ liệu bằng Pydantic để validate trước khi ghi Bronze.
│   ├── silver/         # - Sync Engine & CDC Watermark Tracker (Đồng bộ PostgreSQL ODS).
│   ├── gold/           # - GoldExporter (DWH -> S3 Delta Tables & Parquet fallback).
├── scripts/            # SQL DDL & Migration Scripts (Khởi tạo Schema, CDC & Materialized Views).
├── tests/              # Unit Tests & Integration Tests.
├── docs/               # Tài liệu thiết kế kiến trúc hệ thống, Data Marts chi tiết (Markdown).
├── docker-compose.yml  # File cấu hình khởi chạy toàn bộ services.
├── requirements.txt    # Danh sách thư viện Python phụ thuộc.
```

---

## Tài liệu chi tiết
Vui lòng tham khảo các tài liệu chi tiết trong thư mục `docs/` để hiểu rõ hơn về hệ thống:
* [Hướng dẫn Bảo trì & Tối ưu Dung lượng Docker (WSL2)](file:///d:/JobITVN/job_scraper_de_project/docs/docker_maintenance.md) - Giải pháp dọn dẹp tài nguyên và nén file `.vhdx`.
* Xem chi tiết về các quyết định thiết kế kiến trúc, tổ chức Delta Lakehouse và luồng xử lý ELT tại [docs/README.md](file:///d:/JobITVN/job_scraper_de_project/docs/README.md).

