# Airflow DAGs & Plugins

## Tổng quan

Apache Airflow đóng vai trò **Orchestrator** — lên lịch, điều phối và monitor toàn bộ ETL pipeline. Dự án sử dụng kiến trúc **CeleryExecutor** để chạy các task song song.

---

## Cấu trúc thư mục

```
dags/
├── etl_job_portals_dag.py      ← DAG chính
└── sql/
    ├── create_tables.sql        ← Tạo bảng khi init
    └── upsert_jobs.sql          ← SQL upsert (tham chiếu)

plugins/
├── hooks/
│   └── __init__.py
└── operators/
    ├── __init__.py
    └── scrape_operator.py       ← Custom Operator
```

---

## DAG: `etl_job_portals_dag.py`

### Cấu hình DAG

| Thuộc tính | Giá trị |
|---|---|
| `dag_id` | `etl_job_portals` |
| `schedule_interval` | `0 6 * * *` (6:00 AM mỗi ngày) |
| `start_date` | `2026-01-01` |
| `catchup` | `False` |
| `max_active_runs` | `1` |
| `retries` | `2` |
| `retry_delay` | `timedelta(minutes=5)` |
| `tags` | `["scraping", "etl", "jobs"]` |

### Sơ đồ Task

```
start
  │
  ├──────────────────────────────────────────────────────────┐
  │  [Parallel scraping - mỗi portal là 1 task độc lập]      │
  │                                                          │
  ├── scrape_topcv       ──┐                                 │
  ├── scrape_itviec      ──┤                                 │
  ├── scrape_vietnamworks──┤                                 │
  ├── scrape_jobsgo      ──┤                                 │
  ├── scrape_joboko      ──┤→ transform_and_load_all         │
  ├── scrape_123job      ──┤                                 │
  ├── scrape_careerviet  ──┤                                 │
  ├── scrape_careerlink  ──┤                                 │
  ├── scrape_ybox        ──┤                                 │
  ├── scrape_jobstreet   ──┤                                 │
  └── scrape_linkedin    ──┘                                 │
                                                             │
  └──────────────────────────────────────────────────────────┘
              │
              ▼
        notify_completion   ← Gửi log tổng kết
```

### Task Dependencies

```python
# Extract tasks chạy song song
extract_tasks = [
    scrape_topcv, scrape_itviec, scrape_vietnamworks,
    scrape_jobsgo, scrape_joboko, scrape_123job,
    scrape_careerviet, scrape_careerlink, scrape_ybox,
    scrape_jobstreet, scrape_linkedin
]

# Transform + Load chạy sau khi TẤT CẢ extract tasks hoàn thành
extract_tasks >> transform_and_load_all >> notify_completion
```

### Mô tả từng Task

#### Task Group: `extract`

Mỗi `ScrapeOperator` tự xử lý đầy đủ **3 giai đoạn** bên trong:

| Task ID | Operator | Phase 1 (collect) | Phase 2 (dedup) | Phase 3 (batch detail) |
|---|---|---|---|---|
| `scrape_topcv` | `ScrapeOperator` | Cào N trang list TopCV | Loại URL đã có trong DB | Batch 10 URLs song song |
| `scrape_itviec` | `ScrapeOperator` | Cào N trang list ITViec | Loại URL đã có trong DB | Batch 15 URLs song song |
| `scrape_vietnamworks` | `ScrapeOperator` | Gọi API (không cần Phase 1-3) | Dedup theo `job_url` | N/A |
| `scrape_jobsgo` | `ScrapeOperator` | Cào N trang list JobsGO | Loại URL đã có trong DB | Batch 15 URLs song song |
| `scrape_joboko` | `ScrapeOperator` | Cào N trang list Joboko | Loại URL đã có trong DB | Batch 15 URLs song song |
| `scrape_123job` | `ScrapeOperator` | Cào N trang list 123job | Loại URL đã có trong DB | Batch 10 URLs song song |
| `scrape_careerviet` | `ScrapeOperator` | Cào N trang list CareerViet | Loại URL đã có trong DB | Batch 10 URLs song song |
| `scrape_careerlink` | `ScrapeOperator` | Cào N trang list CareerLink | Loại URL đã có trong DB | Batch 10 URLs song song |
| `scrape_ybox` | `ScrapeOperator` | Cào N trang list Ybox | Loại URL đã có trong DB | Batch 15 URLs song song |
| `scrape_jobstreet` | `ScrapeOperator` | Playwright — cào N trang list | Loại URL đã có trong DB | Batch 5 URLs Playwright |
| `scrape_linkedin` | `ScrapeOperator` | Playwright + cookies | Loại URL đã có trong DB | Batch 3 URLs Playwright |

> Tất cả Phase 3 đều **tắt load image, video, font, stylesheet** để tối ưu tốc độ.

#### Task: `transform_and_load_all`
| Thuộc tính | Giá trị |
|---|---|
| Operator | `PythonOperator` |
| Mô tả | Đọc tất cả raw JSON từ ngày hôm đó → clean → normalize → validate → upsert vào DB |
| Trigger rule | `all_done` (chạy kể cả khi một số scraper thất bại) |

#### Task: `notify_completion`
| Thuộc tính | Giá trị |
|---|---|
| Operator | `PythonOperator` |
| Mô tả | Query DB: tổng số job scraped/inserted/updated theo từng portal hôm nay, log tổng kết |

---

## Custom Operator: `ScrapeOperator`

### File: `plugins/operators/scrape_operator.py`

### Mục đích

Wrap toàn bộ **luồng 3 giai đoạn** (collect URLs → dedup → batch detail fetch) thành một Airflow Operator chuẩn, tái sử dụng cho mọi portal.

### Tham số khởi tạo

| Param | Type | Mô tả |
|---|---|---|
| `source_name` | str | Tên portal: `"topcv"`, `"itviec"`, ... |
| `scraper_class` | type | Class scraper cụ thể (ví dụ: `TopCVScraper`) |
| `pages` | int | Số trang list cào ở Phase 1 (default: `5`) |
| `batch_size` | int | Số URLs fetch song song ở Phase 3 (default: lấy từ `scraper_class.batch_size`) |
| `output_dir` | str | Thư mục lưu raw data (default: `"data/raw"`) |

### Luồng thực thi

```python
class ScrapeOperator(BaseOperator):
    def execute(self, context: Context):
        # 1. Khởi tạo scraper
        scraper = self.scraper_class(
            proxy=Variable.get("PROXY_URL", default_var=None),
            batch_size=self.batch_size,
        )

        # 2. Phase 1: Thu thập URLs từ trang list
        #    Phase 2: Loại URL trùng + URL đã có trong DB
        #    Phase 3: Batch fetch detail (tắt image/video/font/css)
        #    → scraper.run() gọi tuần tự cả 3 phases
        raw_jobs = scraper.run(pages=self.pages)

        # 3. Lưu raw JSON ra disk
        output_path = scraper.save_raw(
            data=raw_jobs,
            date_str=context["ds"]   # YYYY-MM-DD từ Airflow context
        )

        # 4. Push output path + stats vào XCom
        context["ti"].xcom_push(
            key=f"raw_path_{self.source_name}",
            value=str(output_path)
        )
        context["ti"].xcom_push(
            key=f"stats_{self.source_name}",
            value={"total": len(raw_jobs), "source": self.source_name}
        )

        return len(raw_jobs)
```

### XCom flow

```
scrape_topcv.execute()
    ├── xcom_push(key="raw_path_topcv",  value="data/raw/topcv/2026-03-05.json")
    └── xcom_push(key="stats_topcv",     value={"total": 87, "source": "topcv"})

transform_and_load_all.execute()
    ├── xcom_pull(task_ids="scrape_topcv",  key="raw_path_topcv")
    ├── xcom_pull(task_ids="scrape_itviec", key="raw_path_itviec")
    └── ... (tất cả portals)

notify_completion.execute()
    ├── xcom_pull(task_ids="scrape_topcv",  key="stats_topcv")   → {"total": 87}
    ├── xcom_pull(task_ids="scrape_itviec", key="stats_itviec")  → {"total": 102}
    └── ... (tổng hợp thống kê toàn bộ run)
```

---

## Airflow Variables

Lưu trong Airflow UI → Admin → Variables:

| Key | Giá trị mặc định | Mô tả |
|---|---|---|
| `SCRAPE_PAGES` | `5` | Số trang list cào ở Phase 1 mỗi portal |
| `PROXY_URL` | (rỗng) | URL proxy rotation |
| `DB_BATCH_SIZE` | `500` | Số record upsert PostgreSQL mỗi batch |
| `SCRAPE_BATCH_SIZE` | `10` | Số URL fetch song song ở Phase 3 (override mặc định của từng scraper) |
| `BLOCK_RESOURCES` | `image,media,font,stylesheet` | Loại tài nguyên bị chặn khi fetch detail |
| `ENABLE_LINKEDIN` | `false` | Bật/tắt scraper LinkedIn |
| `ENABLE_JOBSTREET` | `true` | Bật/tắt scraper JobStreet |

---

## Airflow Connections

Lưu trong Airflow UI → Admin → Connections:

| Conn ID | Type | Mô tả |
|---|---|---|
| `postgres_job_scraper` | Postgres | Kết nối đến DB job_scraper_db |
| `postgres_default` | Postgres | Kết nối Airflow metadata DB |

---

## Monitoring & Alerting

### SLA Miss
```python
# Nếu DAG không hoàn thành trong 4 tiếng từ lúc trigger:
dag = DAG(
    ...
    sla_miss_callback=sla_miss_alert,
)
```

### Task Failure
```python
default_args = {
    "on_failure_callback": task_failure_alert,
    "email_on_failure": False,   # Dùng callback thay vì email
}
```

### Alert channels (tùy chọn)
- **Slack** webhook: Post message vào channel `#data-alerts`
- **Email**: Gửi qua SMTP config trong Airflow
- **Log**: Ghi vào Airflow logs (luôn bật)

---

## SQL Scripts

### `dags/sql/create_tables.sql`
Chạy khi `airflow-init` để tạo bảng `jobs` và `scrape_logs` nếu chưa tồn tại.

### `dags/sql/upsert_jobs.sql`
SQL template cho `INSERT ... ON CONFLICT DO UPDATE` — được tham chiếu bởi `load_to_dw.py`.

---

## Lịch chạy và phân tích

```
06:00 AM  → DAG trigger (daily)
06:00     → Phase 1: 11 scrapers thu thập URLs song song (Celery workers)
             Mỗi scraper: cào N trang list → chỉ lấy href, rất nhanh
06:05     → Phase 2: Dedup URLs theo DB (query PostgreSQL)
             Chỉ giữ lại URLs thực sự mới
06:05-06:50 → Phase 3: Batch fetch detail song song
             Tắt image/video/font/css → load nhanh hơn 40-70%
             10 URLs/batch × delay 1-3s = ~6s/batch
             Ước tính: 5 trang × ~20 jobs/trang = 100 jobs/portal
             100 jobs ÷ 10 (batch) × 6s ≈ 60s mỗi portal
06:50-07:05 → Transform + Load (clean → normalize → upsert PostgreSQL)
07:05       → Notify completion (log thống kê theo từng portal)

Dữ liệu mới có mặt trong DB trước 07:15 AM mỗi ngày
```
