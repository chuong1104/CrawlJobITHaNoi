# Kiến trúc Tổng thể - Job Scraper DE Project

## Mục tiêu

Xây dựng một **ETL Pipeline tự động** thu thập dữ liệu việc làm từ nhiều trang tuyển dụng Việt Nam, chuẩn hóa về schema thống nhất, và lưu vào Data Warehouse để phục vụ phân tích.

---

## Sơ đồ kiến trúc

```
┌─────────────────────────────────────────────────────────────────┐
│                     Apache Airflow (Orchestrator)               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              DAG: etl_job_portals_dag                    │   │
│  │                                                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │   EXTRACT    │→ │  TRANSFORM   │→ │     LOAD     │   │   │
│  │  │  (Scraping)  │  │  (Cleaning)  │  │  (Upsert DW) │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                     │                    │
         ▼                     ▼                    ▼
┌─────────────────┐   ┌──────────────────┐  ┌─────────────────┐
│  Job Portals    │   │   data/raw/       │  │   PostgreSQL    │
│  (11 websites)  │   │   data/processed/ │  │   Data Warehouse│
└─────────────────┘   └──────────────────┘  └─────────────────┘
```

---

## Các lớp chức năng

### 1. Extract Layer (`src/extract/`)
- **Mục tiêu**: Cào dữ liệu thô từ 11 trang tuyển dụng theo luồng 3 giai đoạn: thu thập URL → lọc trùng → batch cào chi tiết
- **Công nghệ**: [Scrapling](https://github.com/D4Vinci/Scrapling) (HTTP mode & Playwright mode), ThreadPoolExecutor
- **Tối ưu**: Tắt load image/video/font/stylesheet → giảm 40–70% thời gian fetch mỗi trang
- **Output**: File JSON thô lưu vào `data/raw/{portal}/{YYYY-MM-DD}.json`

### 2. Transform Layer (`src/transform/`)
- **Mục tiêu**: Làm sạch và chuẩn hóa dữ liệu thô về schema thống nhất
- **Công nghệ**: Python, Pydantic v2, pandas
- **Output**: List các `JobSchema` object đã validated, lưu vào `data/processed/`

### 3. Load Layer (`src/load/`)
- **Mục tiêu**: Đẩy dữ liệu đã chuẩn hóa vào Data Warehouse
- **Công nghệ**: psycopg2, SQLAlchemy, PostgreSQL `INSERT ON CONFLICT`
- **Output**: Dữ liệu được upsert vào bảng `jobs` trong PostgreSQL

---

## Luồng dữ liệu chi tiết

```
Portal HTML/API
      │
      ▼
Phase 1: collect_urls()      ← Cào N trang list, lấy list job URLs
      │
      ▼
Phase 2: deduplicate_urls()  ← Loại trùng nội bộ + loại URL đã có trong DB
      │
      ▼
Phase 3: fetch_details_batch()  ← Batch song song (10 URLs/batch)
         block image/video/font/stylesheet → HTML thuần
      │
      ▼
*Scraper.parse_job_detail()  ← Scrapling selectors → dict raw
      │
      ▼
List[Dict] (raw)             ← Lưu vào data/raw/
      │
      ▼
Cleaner.clean()              ← Xóa HTML tags, chuẩn hóa text
      │
      ▼
Normalizer.normalize()       ← Chuẩn hóa lương, cấp bậc, job type
      │
      ▼
JobSchema.model_validate()   ← Pydantic validation + type coercion
      │
      ▼
List[JobSchema]              ← Lưu vào data/processed/
      │
      ▼
load_jobs(batch)             ← Batch upsert vào PostgreSQL
      │
      ▼
Table: jobs (PostgreSQL)
```

---

## Chiến lược chống bị chặn (Anti-detection)

| Kỹ thuật | Mô tả | Áp dụng cho |
|---|---|---|
| Random User-Agent | Xoay vòng User-Agent mỗi request | Tất cả |
| Random Delay | Sleep ngẫu nhiên 1-3s giữa các batch | Tất cả |
| Retry + Backoff | Exponential backoff khi gặp lỗi 429/503 | Tất cả |
| Deduplicate trước khi fetch | Không request URL đã có trong DB | Tất cả |
| Block Resources | Chặn image/video/font/stylesheet → giảm tải và vân tay trình duyệt | Tất cả |
| Proxy Rotation | Đổi IP sau N request | Portal chặn mạnh |
| Playwright Stealth | Bypass JavaScript challenge, TLS fingerprinting | JobStreet, LinkedIn |
| Session Cookies | Giữ session đăng nhập | LinkedIn |

---

## Cấu trúc thư mục

```
job_scraper_de_project/
├── docs/                   # 📄 Tài liệu dự án (thư mục này)
├── dags/                   # ✈️  Airflow DAGs & SQL scripts
│   ├── etl_job_portals_dag.py
│   └── sql/
│       ├── create_tables.sql
│       └── upsert_jobs.sql
├── plugins/                # 🔌 Custom Airflow Plugins
│   ├── hooks/
│   └── operators/
│       └── scrape_operator.py
├── src/                    # 💻 Business logic chính
│   ├── extract/            #   → 11 scrapers + BaseScraper
│   ├── transform/          #   → Cleaner, Normalizer, Schemas
│   └── load/               #   → DBConnection, load_to_dw
├── data/
│   ├── raw/                # 📥 JSON thô (không commit)
│   └── processed/          # 📤 JSON đã chuẩn hóa (không commit)
├── tests/                  # 🧪 Unit tests
│   ├── test_extract/
│   └── test_transform/
├── logs/                   # 📋 Airflow logs (không commit)
├── .env                    # 🔑 Credentials (không commit)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Schema thống nhất (JobSchema)

Mọi dữ liệu từ tất cả portal đều được chuẩn hóa về schema này:

| Field | Type | Mô tả |
|---|---|---|
| `job_id` | str | Hash duy nhất: SHA256(source + job_url) |
| `source` | str | Tên portal: "topcv", "itviec", ... |
| `title` | str | Tên vị trí tuyển dụng |
| `company` | str | Tên công ty |
| `location` | str | Tỉnh/thành phố (đã chuẩn hóa) |
| `salary_min` | int \| None | Lương tối thiểu (VND) |
| `salary_max` | int \| None | Lương tối đa (VND) |
| `salary_currency` | str | "VND" hoặc "USD" |
| `job_type` | Enum | FULL_TIME / PART_TIME / CONTRACT / REMOTE |
| `level` | Enum | INTERN / FRESHER / JUNIOR / MID / SENIOR / LEAD / MANAGER |
| `skills` | list[str] | Danh sách kỹ năng yêu cầu |
| `description` | str | Mô tả công việc (đã clean HTML) |
| `requirements` | str | Yêu cầu ứng viên |
| `benefits` | str | Phúc lợi |
| `posted_date` | date | Ngày đăng (ISO 8601) |
| `deadline` | date \| None | Hạn nộp hồ sơ |
| `job_url` | str | URL gốc của job |
| `scraped_at` | datetime | Thời điểm cào dữ liệu |

---

## Công nghệ sử dụng

| Thành phần | Công nghệ | Phiên bản |
|---|---|---|
| Orchestrator | Apache Airflow | 2.8.x |
| Scraping | Scrapling | ≥ 0.2.0 |
| Browser automation | Playwright | ≥ 1.43.0 |
| HTML parsing | BeautifulSoup4 + lxml | ≥ 4.12.0 |
| Data validation | Pydantic | v2 |
| Data processing | pandas | ≥ 2.2.0 |
| Database | PostgreSQL | 15 |
| Message broker | Redis | 7.2 |
| Container | Docker + Compose | - |
| Testing | pytest | ≥ 8.1.0 |
