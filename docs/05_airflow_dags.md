# 05 — Airflow DAGs & Plugins

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Bổ sung hai DAG mới: `nlp_processing_dag` (Giai đoạn 2) và `recommendation_update_dag` (Giai đoạn 4), làm rõ lịch chạy và dependency giữa các DAG.

---

## Tổng quan

Apache Airflow đóng vai trò Orchestrator — lên lịch, điều phối và monitor toàn bộ pipeline. Dự án sử dụng kiến trúc **CeleryExecutor** để chạy các task song song.

Hệ thống có ba DAG chính, mỗi DAG phục vụ một tầng chức năng riêng biệt:

| DAG | Lịch chạy | Mục đích |
|---|---|---|
| `etl_job_portals` | Hàng ngày 06:00 | Thu thập + chuẩn hóa + load jobs mới |
| `nlp_processing` | Hàng ngày 07:30 (sau ETL) | Trích xuất kỹ năng + tạo embedding |
| `recommendation_update` | Hàng tuần CN 02:00 | Cập nhật model gợi ý |

---

## Cấu trúc Thư mục

```
dags/
├── etl_job_portals_dag.py       ← DAG 1: ETL pipeline
├── nlp_processing_dag.py        ← DAG 2: NLP processing [Giai đoạn 2]
├── recommendation_update_dag.py ← DAG 3: Recommendation update [Giai đoạn 4]
└── sql/
    ├── create_tables.sql        ← Tạo tất cả bảng khi init
    └── upsert_jobs.sql          ← SQL upsert tham chiếu

plugins/
├── hooks/
│   └── __init__.py
└── operators/
    ├── __init__.py
    └── scrape_operator.py       ← Custom Operator
```

---

## DAG 1: `etl_job_portals_dag.py`

### Cấu hình

| Thuộc tính | Giá trị |
|---|---|
| `dag_id` | `etl_job_portals` |
| `schedule_interval` | `0 6 * * *` (06:00 hàng ngày) |
| `start_date` | `2026-01-01` |
| `catchup` | `False` |
| `max_active_runs` | `1` |
| `retries` | `2` |
| `retry_delay` | `timedelta(minutes=5)` |
| `tags` | `["etl", "scraping", "jobs"]` |

### Sơ đồ Task

```
start
  │
  ├─ [Song song — mỗi portal là 1 task độc lập]
  │
  ├── scrape_topcv        ──┐
  ├── scrape_itviec       ──┤
  ├── scrape_vietnamworks ──┤
  ├── scrape_jobsgo       ──┤
  ├── scrape_joboko       ──┤──→ transform_and_load_all ──→ notify_completion
  ├── scrape_123job       ──┤
  ├── scrape_careerviet   ──┤
  ├── scrape_careerlink   ──┤
  ├── scrape_ybox         ──┤
  ├── scrape_jobstreet    ──┤
  ├── scrape_linkedin     ──┤
  └── crawl_company_careers┘   ← Task mới: Tier 2 Company Crawlers
```

**Trigger rule cho `transform_and_load_all`:** `all_done` — chạy kể cả khi một số scraper thất bại, đảm bảo dữ liệu từ các nguồn thành công vẫn được xử lý.

### Task `crawl_company_careers` (Mới)

Task này điều phối toàn bộ luồng Tier 2 theo thứ tự nối tiếp:
1. Cập nhật danh sách công ty từ JobsGO (chạy đầy đủ mỗi tuần, chỉ incremental hàng ngày)
2. Cào chi tiết các công ty chưa có `career_url` (crawl_status = 'pending')
3. Tìm career page cho các công ty mới
4. Cào tin tuyển dụng từ career page
5. Lưu raw JSON vào `data/raw/direct/{YYYY-MM-DD}.json`

### Task `transform_and_load_all`

Đọc tất cả raw JSON từ ngày hôm đó (tất cả portal + direct), apply Clean → Normalize → Validate → Upsert. Tổng hợp stats và push vào XCom cho task notify.

### Task `notify_completion`

Query `scrape_logs` để tổng hợp: tổng số jobs mới theo portal, tổng jobs updated, tổng lỗi. Log tổng kết ra Airflow logs. Nếu cấu hình Slack webhook, gửi tóm tắt vào channel `#data-pipeline`.

### Bảng Task chi tiết

| Task ID | Operator | Phase | Ghi chú |
|---|---|---|---|
| `scrape_topcv` | ScrapeOperator | 3 phases | batch_size=10 |
| `scrape_itviec` | ScrapeOperator | 3 phases | batch_size=15, JSON API |
| `scrape_vietnamworks` | ScrapeOperator | API only | Token auth |
| `scrape_jobsgo` | ScrapeOperator | 3 phases | batch_size=15 |
| `scrape_joboko` | ScrapeOperator | 3 phases | batch_size=15 |
| `scrape_123job` | ScrapeOperator | 3 phases | batch_size=10 |
| `scrape_careerviet` | ScrapeOperator | 3 phases | batch_size=10 |
| `scrape_careerlink` | ScrapeOperator | 3 phases | batch_size=10 |
| `scrape_ybox` | ScrapeOperator | 3 phases | batch_size=15 |
| `scrape_jobstreet` | ScrapeOperator | Playwright | batch_size=5 |
| `scrape_linkedin` | ScrapeOperator | Playwright + session | batch_size=3, có thể tắt |
| `crawl_company_careers` | PythonOperator | 4 steps nối tiếp | Tier 2 |
| `transform_and_load_all` | PythonOperator | ETL finish | trigger=all_done |
| `notify_completion` | PythonOperator | Audit | |

---

## DAG 2: `nlp_processing_dag.py` (Giai đoạn 2)

### Mục đích

Xử lý NLP cho các jobs chưa được xử lý (`nlp_processed = FALSE`). DAG này chạy **sau** ETL DAG hoàn thành, đảm bảo dữ liệu mới nhất luôn có embedding và kỹ năng được extract.

### Cấu hình

| Thuộc tính | Giá trị |
|---|---|
| `dag_id` | `nlp_processing` |
| `schedule_interval` | `30 7 * * *` (07:30 hàng ngày) |
| `start_date` | `2026-01-01` |
| `catchup` | `False` |
| `max_active_runs` | `1` |
| `tags` | `["nlp", "embeddings", "skills"]` |

### Sơ đồ Task

```
fetch_unprocessed_jobs
          │
          ▼
skill_extraction_batch ──→ update_job_skills
          │
          ▼
text_embedding_batch   ──→ update_job_embeddings
          │
          ▼
mark_jobs_processed    ──→ nlp_notify_completion
```

### Mô tả Task

**`fetch_unprocessed_jobs`:** Query `SELECT job_id, title, description, requirements, skills FROM jobs WHERE nlp_processed = FALSE LIMIT 5000`. Push danh sách job_id và nội dung vào XCom.

**`skill_extraction_batch`:** Với mỗi job, chạy NLP pipeline trích xuất kỹ năng từ title + description + requirements. Kết quả là list (job_id, skill_id, confidence, position). Xử lý theo batch 100 jobs để không tốn quá nhiều RAM.

**`update_job_skills`:** Bulk upsert kết quả vào bảng `job_skills`. Dùng `INSERT ... ON CONFLICT DO UPDATE` để cập nhật confidence nếu job đã được process trước đây.

**`text_embedding_batch`:** Với mỗi job, tạo embedding vector từ concatenation `title + " " + skills + " " + description[:500]`. Sử dụng model đã cấu hình (PhoBERT hoặc multilingual-e5). Xử lý batch 32 jobs/lần để tận dụng GPU nếu có.

**`update_job_embeddings`:** Bulk upsert vector vào bảng `job_embeddings` (pgvector).

**`mark_jobs_processed`:** `UPDATE jobs SET nlp_processed=TRUE, embedding_ready=TRUE WHERE job_id IN (...)` cho tất cả jobs đã xử lý thành công.

**`nlp_notify_completion`:** Log: số jobs processed, số kỹ năng mới extracted, số embeddings mới tạo, thời gian xử lý trung bình.

### Airflow Variables cho NLP DAG

| Key | Mặc định | Mô tả |
|---|---|---|
| `NLP_BATCH_SIZE` | `100` | Số jobs xử lý mỗi batch skill extraction |
| `EMBEDDING_BATCH_SIZE` | `32` | Số jobs encode mỗi batch |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Tên model embedding |
| `NLP_MAX_JOBS_PER_RUN` | `5000` | Giới hạn jobs xử lý mỗi lần chạy |
| `SKILL_CONFIDENCE_THRESHOLD` | `0.6` | Ngưỡng confidence tối thiểu để lưu |

---

## DAG 3: `recommendation_update_dag.py` (Giai đoạn 4)

### Mục đích

Cập nhật và tái huấn luyện các component của Recommendation System theo lịch tuần, đảm bảo gợi ý phản ánh dữ liệu mới nhất.

### Cấu hình

| Thuộc tính | Giá trị |
|---|---|
| `dag_id` | `recommendation_update` |
| `schedule_interval` | `0 2 * * 0` (02:00 Chủ nhật) |
| `start_date` | `2026-01-01` |
| `catchup` | `False` |
| `tags` | `["recommendation", "ml"]` |

### Sơ đồ Task

```
compute_job_popularity_scores
          │
          ▼
update_skill_job_profiles      ← Tổng hợp skill profile cho từng role
          │
          ▼
compute_job_similarity_matrix  ← Content-based similarity (optional cache)
          │
          ▼
update_trending_skills         ← Cập nhật bảng xu hướng kỹ năng theo tuần
          │
          ▼
recommendation_notify
```

### Mô tả Task

**`compute_job_popularity_scores`:** Tính điểm phổ biến cho mỗi job dựa trên: số lượt xem, số lượt lưu, số lượt apply, và freshness (jobs mới hơn được ưu tiên). Lưu vào cột `popularity_score` trong bảng `jobs`.

**`update_skill_job_profiles`:** Với mỗi role (ví dụ: Data Engineer), aggregate tất cả kỹ năng từ `job_skills` JOIN `jobs WHERE title LIKE '%Data Engineer%'`. Tính tần suất xuất hiện của từng kỹ năng → phân loại Core/Common/Nice-to-have. Lưu vào bảng `role_skill_profiles`.

**`compute_job_similarity_matrix`:** Optional — precompute similarity giữa các jobs phổ biến (top 10,000) và cache kết quả. Giúp tăng tốc content-based recommendation tại runtime.

**`update_trending_skills`:** So sánh tần suất kỹ năng trong jobs của 4 tuần gần nhất. Tính toán trending score = (tần suất tuần này) / (tần suất 4 tuần trước). Lưu vào bảng `skill_trends`.

---

## Custom Operator: `ScrapeOperator`

### Tham số Khởi tạo

| Param | Type | Mô tả |
|---|---|---|
| `source_name` | str | Tên portal định danh |
| `scraper_class` | type | Class scraper cụ thể |
| `pages` | int | Số trang list Phase 1 (default: 5) |
| `batch_size` | int | Số URLs fetch song song Phase 3 |
| `output_dir` | str | Thư mục lưu raw data |

### Luồng Thực thi

```
execute(context):
  1. Khởi tạo scraper với proxy từ Airflow Variable
  2. scraper.run(pages) → Phase 1 + 2 + 3 → list raw dicts
  3. scraper.save_raw(data, date_str) → file JSON
  4. xcom_push("raw_path_{source}", output_path)
  5. xcom_push("stats_{source}", {total, source, errors})
  6. return len(raw_jobs)
```

### XCom Flow

```
scrape_topcv.execute()
  ├── xcom_push(key="raw_path_topcv",  value="data/raw/topcv/2026-03-11.json")
  └── xcom_push(key="stats_topcv",     value={"total": 87, "errors": 2})

transform_and_load_all.execute()
  ├── xcom_pull(task_ids="scrape_topcv",  key="raw_path_topcv")
  ├── xcom_pull(task_ids="scrape_itviec", key="raw_path_itviec")
  └── ... (tất cả portals + direct)

notify_completion.execute()
  ├── xcom_pull(task_ids="scrape_topcv",  key="stats_topcv")  → 87 jobs
  └── ... (tổng hợp toàn bộ run)
```

---

## Airflow Variables

| Key | Mặc định | Mô tả |
|---|---|---|
| `SCRAPE_PAGES` | `5` | Số trang list mỗi portal |
| `PROXY_URL` | `""` | URL proxy rotation |
| `DB_BATCH_SIZE` | `500` | Records upsert mỗi batch |
| `SCRAPE_BATCH_SIZE` | `10` | URLs fetch song song |
| `BLOCK_RESOURCES` | `image,media,font,stylesheet` | Resources bị chặn |
| `ENABLE_LINKEDIN` | `false` | Bật/tắt LinkedIn scraper |
| `ENABLE_JOBSTREET` | `true` | Bật/tắt JobStreet scraper |
| `ENABLE_COMPANY_CRAWL` | `true` | Bật/tắt Tier 2 company crawlers |
| `COMPANY_CRAWL_LIMIT` | `50` | Số công ty crawl career page mỗi ngày |
| `NLP_BATCH_SIZE` | `100` | Batch size cho NLP DAG |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Model embedding |

---

## Airflow Connections

| Conn ID | Type | Mô tả |
|---|---|---|
| `postgres_job_scraper` | Postgres | Job Scraper Data Warehouse |
| `postgres_default` | Postgres | Airflow metadata DB |
| `slack_webhook` | HTTP | Slack alert (optional) |

---

## Monitoring & Alerting

**SLA Miss:** Nếu `etl_job_portals` không hoàn thành trong 4 giờ từ lúc trigger (10:00 AM), gọi `sla_miss_callback`.

**Task Failure:** `on_failure_callback` ghi log và gửi Slack alert (nếu cấu hình). Email notification bị tắt mặc định, thay bằng callback.

**Channels:**
- Slack webhook: channel `#data-pipeline-alerts`
- Airflow logs: luôn bật

---

## Lịch Chạy và Ước tính Thời gian

```
06:00 AM — etl_job_portals trigger
06:00 → 06:05   Phase 1: 11 scrapers + company crawlers thu thập URLs (song song)
06:05           Phase 2: Dedup URLs theo DB
06:05 → 06:50   Phase 3: Batch fetch detail song song (tắt image/video/font/css)
                  Ước tính: 5 trang × 20 jobs/trang = 100 jobs/portal
                  100 jobs ÷ 10 (batch) × 6s/batch ≈ 60s mỗi portal
06:50 → 07:00   Transform + Load (clean → normalize → upsert PostgreSQL)
07:00           Notify ETL completion

07:30 AM — nlp_processing trigger
07:30 → 09:00   Skill extraction + Text embedding cho jobs mới
                  Ước tính: 500 jobs mới × ~3s/job (NLP) = ~25 phút

02:00 AM CN — recommendation_update trigger
02:00 → 03:00   Cập nhật popularity scores, role profiles, trending skills

→ Dữ liệu mới (jobs cơ bản) có trong DB trước 07:10 AM
→ Dữ liệu NLP đầy đủ (search semantic, recommendation) có trước 09:30 AM
```
