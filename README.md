# JobITVN: Local AWS Lakehouse Data Pipeline

Hệ thống thu thập, phân tích dữ liệu việc làm từ các trang tuyển dụng Việt Nam. Dự án được xây dựng theo kiến trúc **Local AWS Lakehouse (Modern Data Stack)** tiên tiến nhất hiện nay, giả lập hoàn hảo môi trường AWS trên Local nhưng tiêu tốn cực kỳ ít tài nguyên.

---

## 🚀 Công nghệ sử dụng (The Modern Data Stack)

| Layer | Công cụ | Vai trò |
|---|---|---|
| **Orchestration** | **Apache Airflow** | Lập lịch và điều phối toàn bộ vòng đời ETL/ELT pipeline. Tự động chạy hàng ngày, xử lý lỗi và retry. |
| **Data Collection** | **Scrapling & Playwright** | Thu thập dữ liệu hiệu suất cao. `Scrapling` dùng cho trang tĩnh. `Playwright` dùng cho trang SPA (JS-rendered) và chống bot. |
| **Local Cloud Emulator** | **Floci** | Giả lập môi trường đám mây AWS ngay trên máy cá nhân. Cực nhẹ (chỉ tốn ~13MB RAM), khởi động trong 24ms. |
| **Data Lake Storage** | **Floci S3** | Lưu trữ toàn bộ dữ liệu tập trung theo mô hình Medallion (Bronze, Silver, Gold). Đảm bảo tính Immutable. |
| **Compute Engine** | **DuckDB** | Đóng vai trò là cỗ máy phân tích (Analytical Engine) truy vấn siêu tốc thẳng vào file Parquet trên S3. |
| **Transformation** | **dbt-core** | Thực hiện làm sạch, trích xuất dữ liệu (parse mức lương, kỹ năng) và xây dựng Star Schema hoàn toàn bằng SQL. |
| **Serving** | **FastAPI & Power BI** | API phân phối dữ liệu cho Web Portal và Dashboard báo cáo BI phục vụ phân tích thị trường. |

---

## 🏗 Kiến trúc Pipeline (ELT)

Dữ liệu di chuyển theo chuẩn **Medallion Architecture**, tách biệt hoàn toàn Storage (S3) và Compute (DuckDB):

```text
[Apache Airflow]
       │
       ├── 1. [EXTRACT & LOAD] Scraper Pipeline
       │       └── Crawl dữ liệu -> Pydantic Validation -> Lưu file JSONL/JSON gốc (Append-only).
       │       └── Đẩy dữ liệu trực tiếp lên Floci S3: `s3://jobit-bronze/year=.../month=.../`
       │
       └── 2. [TRANSFORM] dbt + DuckDB
               ├── Tầng Silver (Cleaned):
               │    └── Đọc S3 Bronze -> Parse mức lương chuẩn, xử lý ngày tháng, chuẩn hoá địa điểm.
               │    └── Ghi file Parquet tối ưu hoá đọc tại `s3://jobit-silver`.
               ├── Tầng Intermediate (Business Logic):
               │    └── Lọc trùng lặp (Deduplication), sử dụng regex trích xuất kỹ năng (Skill extraction).
               └── Tầng Gold (Data Marts):
                    └── Xây dựng Star Schema (Fact/Dim). Phục vụ trực tiếp BI Dashboard & API.
                    └── Ghi file Parquet cuối cùng tại `s3://jobit-gold`.
```

---

## 🌐 Các nguồn dữ liệu đang hỗ trợ

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

## Hướng dẫn cấu hình Cookie cho LinkedIn

LinkedIn áp dụng các biện pháp chặn bot vô cùng khắt khe. Nếu request liên tục mà không duy trì phiên đăng nhập hợp lệ, tài khoản của bạn hoặc IP sẽ bị khóa. Hệ thống giải quyết việc này bằng cách lưu trữ **Session Cookie** để mô phỏng người dùng thật.

**Cách 1: Khởi tạo cookie tự động qua Playwright UI (Khuyến nghị cho Local)**
Chạy script dưới đây. Một cửa sổ trình duyệt Chromium sẽ bật lên để bạn tự tay nhập tài khoản, mật khẩu và giải CAPTCHA (nếu có). Sau khi login thành công, hệ thống tự động trích xuất cookie và đóng trình duyệt.
```bash
python scripts/login_linkedin_interactive.py
```
> [!NOTE]
> Cookie được lưu tự động tại thư mục: `src/extract/job_online/auth/linkedin_state.json`. Thư mục này đã được thêm vào `.gitignore` để tránh rò rỉ phiên đăng nhập của bạn lên Git. Khi container Docker khởi chạy, nó sẽ tự động mount thư mục `src` này vào trong và sử dụng lại file JSON đó.

**Cách 2: Chèn cookie thủ công (Manual Import)**
Nếu bạn chạy trên máy chủ không có giao diện UI (headless server) hoặc cách 1 bị lỗi:
1. Mở trình duyệt Chrome/Edge của bạn trên máy tính cá nhân.
2. Đăng nhập vào trang chủ LinkedIn.
3. Cài đặt extension [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg).
4. Sử dụng extension này để Xuất (Export) toàn bộ cookie của LinkedIn ra định dạng JSON copy vào clipboard.
5. Tạo một file tên là `linkedin_state.json` theo đường dẫn `src/extract/job_online/auth/linkedin_state.json` và Paste nội dung vừa copy vào đó.
6. Hệ thống Scraper của LinkedIn (`LinkedInPlaywrightScraper`) sẽ tự động đọc file này khi hoạt động.

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

Mở file `.env` vừa tạo để xem và chỉnh sửa (nếu cần). Các thông số mặc định đã được thiết lập sẵn để chạy local:
- `POSTGRES_USER`, `POSTGRES_PASSWORD`: Tài khoản cho database nội bộ của Airflow.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: Thông tin xác thực ảo dùng để giao tiếp với Floci S3.
- *Lưu ý:* Nếu bạn cần cào dữ liệu từ LinkedIn, hãy điền thông tin tài khoản vào `LINKEDIN_USERNAME` và `LINKEDIN_PASSWORD` trong file `.env`.

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
Quá trình tải image và build lần đầu có thể mất vài phút. Sau khi hoàn thành, kiểm tra trạng thái các container:
```bash
docker compose ps
```
> [!TIP]
> **Airflow Web UI** hiện đã có thể truy cập tại: **http://localhost:8080**
> Tài khoản mặc định: `admin` / Mật khẩu: `admin`

### 5. Khởi tạo Data Lake (S3 Buckets)
Trình giả lập AWS (Floci) ban đầu sẽ trống rỗng. Bạn cần chạy lệnh sau (chỉ 1 lần duy nhất) để tạo các bucket `jobit-bronze`, `jobit-silver`, `jobit-gold`:
```bash
docker compose exec airflow env PYTHONPATH=/opt/airflow python -m src.storage.init_buckets
```

### 6. Thực thi Crawling Dữ Liệu (Extraction)
Chạy script để kích hoạt các scrapers. Dữ liệu thô thu thập được (JSON/HTML) sẽ được tự động stream lên bucket `jobit-bronze`.

```bash
# Chạy cào toàn bộ (full) với 4 luồng song song
docker compose exec airflow env PYTHONPATH=/opt/airflow python /opt/airflow/scripts/run_scrapers.py --mode full --workers 4

# Hoặc chỉ chạy test thử 2 trang đầu tiên cho mỗi nguồn
docker compose exec airflow env PYTHONPATH=/opt/airflow python /opt/airflow/scripts/run_scrapers.py --mode full --pages 2 --workers 2
```

*(Tuỳ chọn)* Nếu bạn muốn cập nhật session cookie của LinkedIn qua trình duyệt mở tự động:
```bash
docker compose exec airflow python /opt/airflow/scripts/login_linkedin_interactive.py
```

### 7. Xử lý và Chuyển đổi Dữ liệu (Transformation) với dbt
Sau khi quá trình cào dữ liệu hoàn tất, chúng ta dùng `dbt` và `DuckDB` để làm sạch, trích xuất kỹ năng, và gom dữ liệu thành các mô hình bảng phục vụ phân tích.

Thực thi dbt bên trong container Airflow:
```bash
# 1. Kiểm tra kết nối cấu hình dbt
docker compose exec airflow dbt debug --profiles-dir ./dbt_jobitvn --project-dir ./dbt_jobitvn

# 2. Chạy toàn bộ pipeline ETL (từ Bronze -> Silver -> Gold)
docker compose exec airflow dbt run --profiles-dir ./dbt_jobitvn --project-dir ./dbt_jobitvn

# 3. Chạy kiểm thử chất lượng dữ liệu (Data Quality Tests)
docker compose exec airflow dbt test --profiles-dir ./dbt_jobitvn --project-dir ./dbt_jobitvn
```

### 8. Quản lý vòng đời dữ liệu (Nén dữ liệu cũ)
Dự án có module tự động nén các file thô JSON cũ thành file Parquet (chuẩn nén ZSTD) để tiết kiệm 70-90% dung lượng trên Data Lake.
```bash
docker compose exec airflow env PYTHONPATH=/opt/airflow python -m src.lifecycle.bronze_archiver
```

### 9. Tương tác với hệ thống lưu trữ bằng AWS CLI
Bạn có thể kết nối với Floci S3 y hệt như AWS S3 thật bằng công cụ `aws-cli` (nếu có cài trên máy):
```bash
# Liệt kê danh sách các folder/file trong tầng Bronze
aws --endpoint-url=http://localhost:4566 s3 ls s3://jobit-bronze/ --recursive

# Tải hoặc xem một file cụ thể
aws --endpoint-url=http://localhost:4566 s3 cp s3://jobit-bronze/valid/source=topcv/... -
```
---

## Cấu trúc thư mục chi tiết

Dự án được tổ chức theo tiêu chuẩn của một Data Platform hiện đại, chia tách rõ ràng các tầng nghiệp vụ:

```text
job_scraper_de_project/
├── dags/               # Airflow DAGs: Định nghĩa lịch trình chạy pipeline tự động (Daily/Weekly).
│   └── daily_pipeline.py
├── dbt_jobitvn/        # dbt Project: Toàn bộ logic Transform bằng SQL (Models, Tests, Seeds).
├── src/                # Mã nguồn chính (Core Python Logic):
│   ├── config.py       # - Quản lý cấu hình toàn cục (Environment variables, Paths).
│   ├── utils.py        # - Các hàm tiện ích dùng chung (Logger, Text normalizers).
│   ├── extract/        # - (E - Extract) Module thu thập dữ liệu bằng Playwright & Scrapy cho 9 nguồn (TopCV, LinkedIn,...).
│   ├── storage/        # - (Storage Layer) Module giao tiếp trực tiếp với Data Lake (Floci S3) thông qua Boto3.
│   ├── schema/         # - (Data Contract) Định nghĩa cấu trúc dữ liệu bằng Pydantic để validate trước khi lưu.
│   ├── lifecycle/      # - (Data Lifecycle) Quản lý vòng đời: Tự động nén (Archive) dữ liệu cũ sang Parquet ZSTD.
│   ├── silver/         # - (Python Transform) Logic làm sạch phức tạp nếu không thể viết bằng SQL dbt.
│   ├── gold/           # - (Python Transform) Logic tổng hợp hoặc Export dữ liệu đặc thù.
│   └── sync/           # - (Sync) Đồng bộ hóa dữ liệu từ Lakehouse ra các hệ thống bên ngoài (VD: ElasticSearch).
├── scripts/            # Executable Scripts (Công cụ tiện ích chạy tay):
│   ├── run_scrapers.py # - Tool kích hoạt cào dữ liệu song song (Multi-processing) để test nhanh.
│   └── login_linkedin_interactive.py # - Tool giả lập trình duyệt để lấy Session Cookie cho các trang chặn bot.
├── tests/              # Unit Tests & Integration Tests đảm bảo logic không bị gãy khi update.
├── data/               # Local Data Mount (Thư mục map với Floci S3 và Postgres):
│   ├── floci/          # - Nơi lưu trữ vật lý các buckets S3 giả lập của Floci.
│   ├── bronze/         # - Tầng 1 (Raw): Dữ liệu thô nguyên bản chưa qua xử lý (JSON).
│   ├── silver/         # - Tầng 2 (Clean): Dữ liệu đã chuẩn hóa, lọc trùng, trích xuất kỹ năng (Parquet).
│   └── gold/           # - Tầng 3 (Aggregated): Dữ liệu phân tích mô hình Star Schema (Parquet).
├── docs/               # Tài liệu thiết kế kiến trúc hệ thống, Data Marts chi tiết (Markdown).
├── docker-compose.yml  # File cấu hình khởi chạy toàn bộ 3 block chính: Postgres, Floci S3, Airflow.
├── .env                # File cấu hình secret keys và biến môi trường (Local Only).
└── requirements.txt    # Danh sách thư viện Python phụ thuộc của toàn dự án.
```

---

## Tài liệu chi tiết
Vui lòng tham khảo thư mục `docs/` để đọc chi tiết về các quyết định thiết kế kiến trúc, tổ chức Data Lakehouse và luồng xử lý ELT.
