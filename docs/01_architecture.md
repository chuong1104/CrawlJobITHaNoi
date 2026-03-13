# 01 — Kiến trúc Tổng thể — JobInsight Platform

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Tài liệu này mô tả kiến trúc toàn hệ thống, bao gồm cả lớp ETL Pipeline cốt lõi lẫn các lớp NLP, Search, Recommendation và Web Application được bổ sung theo tầm nhìn nền tảng tình báo thị trường việc làm.

---

## Mục tiêu Hệ thống

Xây dựng **JobInsight Platform** — một nền tảng tích hợp gồm hai phần liên kết chặt chẽ:

**Phần 1 — Data Engineering Core:** ETL Pipeline tự động thu thập dữ liệu việc làm từ ≥ 11 portal tuyển dụng Việt Nam và từ career page trực tiếp của các công ty, chuẩn hóa về schema thống nhất, và lưu vào Data Warehouse.

**Phần 2 — Intelligence Layer:** Ứng dụng NLP, Information Retrieval, Recommendation System, và Learning Path Guidance trên nền dữ liệu đã thu thập, phục vụ tìm kiếm thông minh và hỗ trợ định hướng nghề nghiệp cho sinh viên mới tốt nghiệp và người có 0–2 năm kinh nghiệm.

---

## Sơ đồ Kiến trúc Tổng thể

```
┌──────────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER — Apache Airflow                   │
│                                                                          │
│   DAG: etl_job_portals   DAG: nlp_processing   DAG: recommendation_update│
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
            ┌──────────────────────▼──────────────────────┐
            │           DATA COLLECTION LAYER              │
            │                                              │
            │  ┌──────────────────┐  ┌──────────────────┐ │
            │  │  Portal Scrapers  │  │  Company Crawlers│ │
            │  │  (11 websites)    │  │  (Career Pages)  │ │
            │  └────────┬─────────┘  └────────┬─────────┘ │
            └───────────┼────────────────────┼────────────┘
                        │                    │
                        ▼                    ▼
            ┌───────────────────────────────────────────────┐
            │          DATA PIPELINE & WAREHOUSE            │
            │                                               │
            │  data/raw/  →  Transform  →  PostgreSQL DW   │
            │  (JSON thô)    (Clean +       (jobs, skills,  │
            │                Normalize +    companies,      │
            │                Validate)      embeddings)     │
            └───────────────────────┬───────────────────────┘
                                    │
            ┌───────────────────────▼───────────────────────┐
            │             NLP PROCESSING LAYER              │
            │                                               │
            │  Skill Extraction (NER + Dictionary)          │
            │  Text Embedding (PhoBERT / multilingual-e5)   │
            │  Job Classification · Salary Analysis         │
            └───────────────────────┬───────────────────────┘
                                    │
       ┌────────────────────────────▼────────────────────────────┐
       │              INTELLIGENCE & SEARCH LAYER                │
       │                                                         │
       │  Hybrid Search (BM25 + Semantic + Structured Filter)    │
       │  Recommendation Engine (Content + Collab + Knowledge)   │
       │  Skill Gap Analysis · Learning Path Generator           │
       └────────────────────────────┬────────────────────────────┘
                                    │
            ┌───────────────────────▼───────────────────────┐
            │           WEB APPLICATION LAYER               │
            │                                               │
            │  FastAPI Backend (REST API)                   │
            │  Next.js Frontend (SSR)                       │
            │  Redis Cache · pgvector Search                │
            └───────────────────────────────────────────────┘
```

---

## Các Lớp Chức năng Chi tiết

### Lớp 1 — Data Collection (`src/extract/`)

**Mục tiêu:** Thu thập dữ liệu thô theo luồng ba giai đoạn — thu thập URL danh sách → lọc trùng → batch cào chi tiết song song.

**Hai nguồn dữ liệu song song:**
- **Tier 1 — Portal Scrapers:** 11 scraper cho các portal tuyển dụng lớn, sử dụng Scrapling (HTTP mode) và Playwright (JS-heavy portals).
- **Tier 2 — Company Crawlers:** Crawler thu thập danh sách công ty từ JobsGO → tìm career page chính thức → cào tin tuyển dụng trực tiếp, đánh dấu `source = "direct"`.

**Tối ưu hiệu suất:** Tắt tải image/video/font/stylesheet → giảm 40–70% thời gian fetch. Batch song song 10 URLs/batch với ThreadPoolExecutor.

**Output:** File JSON thô tại `data/raw/{source}/{YYYY-MM-DD}.json`.

### Lớp 2 — Data Pipeline & Warehouse (`src/transform/`, `src/load/`)

**Mục tiêu:** Biến dữ liệu thô, không đồng nhất từ nhiều nguồn thành tập dữ liệu sạch, nhất quán trong một schema duy nhất.

**Ba bước xử lý nối tiếp:**
- **Cleaner:** Xóa HTML tags, chuẩn hóa encoding, parse ngày tháng đa format.
- **Normalizer:** Chuẩn hóa lương về VND, cấp bậc về Enum, địa điểm về tên chuẩn.
- **Schema Validator (Pydantic v2):** Type coercion, business rule validation, tạo `job_id` idempotent bằng SHA256(source + job_url).

**Load chiến lược:** `INSERT ... ON CONFLICT DO UPDATE` vào PostgreSQL, chỉ cập nhật khi `scraped_at` mới hơn, tránh ghi thừa.

### Lớp 3 — NLP Processing (`src/nlp/`)

**Mục tiêu:** Trích xuất thông tin có cấu trúc từ văn bản mô tả công việc, tạo ra biểu diễn ngữ nghĩa phục vụ tìm kiếm và gợi ý.

Bốn thành phần chính: Skill Extraction (NER + dictionary matching), Text Embedding (vector hóa ngữ nghĩa), Job Classification (phân ngành), Salary Analysis (parse và impute lương ẩn). Chi tiết trong tài liệu `05_nlp_processing.md`.

### Lớp 4 — Intelligence & Search (`src/search/`, `src/recommendation/`, `src/learning/`)

**Mục tiêu:** Tạo ra giá trị thực cho người dùng cuối từ dữ liệu đã được xử lý.

- **Hybrid Search:** Kết hợp BM25 (sparse) và Semantic Search (dense vector) qua Reciprocal Rank Fusion, cho phép tìm kiếm theo kỹ năng/công cụ xuất hiện trong mô tả thay vì chỉ theo tiêu đề.
- **Recommendation Engine:** Đa tầng — Content-based → Collaborative → Knowledge-based → Hybrid Ensemble.
- **Skill Gap & Learning Path:** Phân tích khoảng cách kỹ năng theo Skill Dependency Graph, sinh lộ trình học có thứ tự và nguồn học cụ thể.

### Lớp 5 — Web Application (`app/`)

**Mục tiêu:** Giao diện người dùng cho nền tảng tìm việc thông minh.

FastAPI backend phục vụ REST API, Next.js frontend với SSR cho SEO. Redis cache kết quả tìm kiếm và session. Chi tiết trong tài liệu `08_web_application.md`.

---

## Luồng Dữ liệu Chi tiết — ETL Core

```
Portal HTML / API / Career Page
          │
          ▼
Phase 1: collect_urls()
  └─ Cào N trang list, lấy danh sách job URLs

          │
          ▼
Phase 2: deduplicate_urls()
  └─ Loại trùng nội bộ + loại URL đã có trong DB (query PostgreSQL)

          │
          ▼
Phase 3: fetch_details_batch()
  └─ Batch song song (10 URLs/batch)
  └─ Block: image / video / font / stylesheet

          │
          ▼
*Scraper.parse_job_detail()
  └─ Scrapling selectors → dict raw

          │
          ▼
List[Dict] (raw)  →  Lưu vào data/raw/

          │
          ▼
Cleaner.clean()
  └─ Xóa HTML, parse date, chuẩn hóa whitespace

          │
          ▼
Normalizer.normalize()
  └─ Chuẩn hóa lương, cấp bậc, job type, location

          │
          ▼
JobSchema.model_validate()
  └─ Pydantic v2 validation + tạo job_id (SHA256)

          │
          ▼
List[JobSchema]  →  Lưu vào data/processed/

          │
          ▼
load_jobs(batch)
  └─ Batch upsert vào PostgreSQL (INSERT ON CONFLICT)

          │
          ▼
Table: jobs (PostgreSQL)
          │
          ▼ (async — NLP DAG)
NLP Pipeline
  └─ Skill Extraction → job_skills table
  └─ Text Embedding   → job_embeddings table (pgvector)
```

---

## Schema Thống nhất (JobSchema)

Mọi dữ liệu từ tất cả nguồn đều được chuẩn hóa về schema này trước khi lưu vào warehouse:

| Field | Type | Mô tả |
|---|---|---|
| `job_id` | str | SHA256(source + job_url)[:16] — idempotent |
| `source` | str | Tên portal: "topcv", "itviec", "direct", ... |
| `title` | str | Tên vị trí tuyển dụng |
| `company` | str | Tên công ty |
| `location` | str | Tỉnh/thành phố (đã chuẩn hóa) |
| `salary_min` | int \| None | Lương tối thiểu (VND) |
| `salary_max` | int \| None | Lương tối đa (VND) |
| `salary_currency` | str | "VND" hoặc "USD" |
| `job_type` | Enum | FULL_TIME / PART_TIME / CONTRACT / REMOTE |
| `level` | Enum | INTERN / FRESHER / JUNIOR / MID / SENIOR / LEAD / MANAGER |
| `skills` | list[str] | Kỹ năng từ scraper (raw, chưa qua NLP extraction) |
| `description` | str | Mô tả công việc (đã clean HTML) |
| `requirements` | str | Yêu cầu ứng viên |
| `benefits` | str | Phúc lợi |
| `posted_date` | date | Ngày đăng (ISO 8601) |
| `deadline` | date \| None | Hạn nộp hồ sơ |
| `job_url` | str | URL gốc |
| `scraped_at` | datetime | Thời điểm cào |

---

## Chiến lược Chống Phát hiện (Anti-detection)

| Kỹ thuật | Mô tả | Áp dụng cho |
|---|---|---|
| Random User-Agent | Xoay vòng mỗi request | Tất cả |
| Random Delay | Sleep 1–3s giữa các batch | Tất cả |
| Retry + Exponential Backoff | Khi nhận 429/503 | Tất cả |
| Deduplicate trước khi fetch | Không request URL đã có trong DB | Tất cả |
| Block Resources | Chặn image/video/font/stylesheet | Tất cả |
| Proxy Rotation | Đổi IP sau N request | Portal chặn mạnh |
| Playwright Stealth | Bypass JS challenge, TLS fingerprint | JobStreet, LinkedIn |
| Session Cookies | Giữ session đăng nhập | LinkedIn |
| robots.txt compliance | Tuân thủ giới hạn tốc độ theo ToS | Tất cả |

---

## Cấu trúc Thư mục Dự án

```
job_scraper_de_project/
├── docs/                        # Tài liệu dự án
│   ├── 00_project_overview.md
│   ├── 01_architecture.md       ← File này
│   ├── 02_extract.md
│   ├── 03_transform.md
│   ├── 04_load.md
│   ├── 05_airflow_dags.md
│   ├── 06_infrastructure.md
│   ├── 07_testing.md
│   ├── 08_scrapling_portals_reference.md
│   ├── 09_scrapling_usage_guide.md
│   └── 10_website_source_analysis.md
│   └── 11_company_career_analysis.md
│   └── README.md
│
├── dags/                        # Airflow DAGs
│   ├── etl_job_portals_dag.py
│   ├── nlp_processing_dag.py    ← [Giai đoạn 2]
│   ├── recommendation_dag.py    ← [Giai đoạn 4]
│   └── sql/
│       ├── create_tables.sql
│       └── upsert_jobs.sql
│
├── plugins/                     # Custom Airflow Plugins
│   ├── hooks/
│   └── operators/
│       ├── __init__.py
│       └── scrape_operator.py
│
├── src/                         # Business logic
│   ├── extract/
│   │   ├── job_online/          # 11 portal scrapers
│   │   │   ├── base_scraper.py
│   │   │   ├── topcv.py
│   │   │   ├── itviec.py
│   │   │   ├── vietnamworks.py
│   │   │   ├── jobsgo.py
│   │   │   ├── joboko.py
│   │   │   ├── job_123.py
│   │   │   ├── careerviet.py
│   │   │   ├── careerlink.py
│   │   │   ├── ybox.py
│   │   │   └── linkedin.py
│   │   ├── company/
│   │   │   └── jobsgo_company_crawler.py
│   ├── transform/
│   │   ├── cleaner.py
│   │   ├── normalizer.py
│   │   └── schemas.py
│   ├── load/
│   │   ├── db_connection.py
│   │   └── load_to_dw.py
│   ├── config.py
│   ├── utils.py
│
├── data/
│   ├── raw/
│   │   ├── careerlink/
│   │   ├── careerviet/
│   │   ├── itviec/
│   │   ├── job123/
│   │   ├── joboko/
│   │   ├── jobsgo/
│   │   ├── topcv/
│   │   ├── vietnamworks/
│   │   ├── ybox/
│   │   └── ...
│   ├── processed/
│   ├── company_list_jobsgo.csv
│   ├── company_url_list_jobsgo.csv
│
├── tests/
│   ├── test_extract/
│   ├── test_transform/
│   └── ...
│
├── logs/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Data Model Mở rộng

Ngoài bảng `jobs` cốt lõi, hệ thống bổ sung các bảng phục vụ tính năng NLP và Intelligence:

```
jobs (job_id PK, source, title, company, location, salary_*, job_type, level,
      skills[], description, requirements, benefits, posted_date, deadline,
      job_url, scraped_at, created_at, updated_at)

job_skills (job_id FK, skill_id FK, confidence FLOAT, position: title|desc|req)

skills (skill_id PK, name, category, aliases[], parent_skill_id, difficulty_level)

skill_prerequisites (skill_id FK, prerequisite_skill_id FK, is_hard_requirement BOOL)

job_embeddings (job_id FK, embedding VECTOR(768), model_name, created_at)

companies (company_id PK, name, website, career_url, industry, size, location,
           source_portal, crawled_at)

users (user_id PK, email, target_role, experience_years, location_pref,
       salary_expectation, created_at, last_active_at)

user_skills (user_id FK, skill_id FK, proficiency_level, source: declared|inferred)

user_interactions (interaction_id PK, user_id FK, job_id FK,
                   action_type: view|save|apply|skip, timestamp, session_id)

user_learning_paths (user_id FK, target_role, progress_pct, milestone_completions[],
                     created_at, updated_at)

learning_resources (resource_id PK, title, url, platform, resource_type,
                    duration_hours, cost, language, rating, skills_covered[],
                    last_verified_at)

scrape_logs (id PK, run_id, source, started_at, finished_at, status,
             jobs_scraped, jobs_inserted, jobs_updated, jobs_skipped, error_message)
```

---

## Công nghệ Sử dụng

| Thành phần | Công nghệ | Phiên bản |
|---|---|---|
| Orchestrator | Apache Airflow | 2.8.x |
| Scraping (HTTP) | Scrapling | ≥ 0.2.0 |
| Scraping (JS) | Playwright | ≥ 1.43.0 |
| HTML Parsing | BeautifulSoup4 + lxml | ≥ 4.12.0 |
| Data Validation | Pydantic | v2 |
| Data Processing | pandas | ≥ 2.2.0 |
| NLP (Vietnamese) | PhoBERT (VinAI) | — |
| NLP (Multilingual) | multilingual-e5 | — |
| NLP (NER) | spaCy | ≥ 3.7.0 |
| Vector Storage | pgvector (PostgreSQL ext) | — |
| Database | PostgreSQL | 15 |
| Cache / Broker | Redis | 7.2 |
| Backend API | FastAPI | ≥ 0.110.0 |
| Frontend | Next.js | 14.x |
| Container | Docker + Compose | — |
| Monitoring | Prometheus + Grafana | — |
| Testing | pytest | ≥ 8.1.0 |
