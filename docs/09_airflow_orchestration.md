# 09. Airflow Orchestration

## 1. Mục tiêu

Hệ thống cần tự động điều phối toàn bộ các công đoạn của vòng đời dữ liệu một cách trơn tru, bao gồm:
* Thu thập dữ liệu việc làm từ nhiều nguồn song song.
* Chuyển đổi tầng Staging/Intermediate thông qua dbt DuckDB.
* Đồng bộ và chuẩn hóa vào cơ sở dữ liệu Silver PostgreSQL (3NF) kèm xử lý SCD Type 2 & Trigram Aliasing.
* Xây dựng kho dữ liệu Gold DWH và refresh các materialized views phục vụ Web API.
* Export dữ liệu Marts ra S3 Delta tables phục vụ ML và Power BI.
* Bảo trì hệ thống (VACUUM Delta Tables và Archive dữ liệu JSON thô cũ).

Toàn bộ luồng được Apache Airflow điều phối tự động qua một DAG chính chạy hàng ngày.

---

## 2. Thiết kế và Lập lịch DAG

Kiến trúc điều phối sử dụng một DAG duy nhất: **`daily_job_pipeline`** (định nghĩa tại [daily_pipeline.py](file:///d:/JobITVN/job_scraper_de_project/dags/daily_pipeline.py)).

### Lập lịch (Schedule)
* **Thời gian chạy:** 6:00 sáng hàng ngày (Giờ Việt Nam - `0 6 * * *`).
* **Catchup:** `False` (không chạy bù các ngày cũ).
* **Owner:** `data-platform`.

---

## 3. Kiến trúc Luồng Công Việc (Task Dependencies)

Luồng chạy của DAG được thiết kế tối ưu hóa song song bằng cách chia nhánh ngay sau khi kết thúc bước biến đổi Staging:

```text
       ┌───────────┐
       │   start   │
       └─────┬─────┘
             ▼
 ┌───────────────────────┐
 │   crawl_all_sources   │  (Chạy run_scrapers.py, đẩy metrics lên XCom)
 └───────────┬───────────┘
             ▼
 ┌───────────────────────┐
 │    run_dbt_staging    │  (dbt: Staging & Intermediate DuckDB)
 └─────┬───────────┬─────┘
       │           ├─────────────────────────┐
       ▼           ▼                         ▼
 ┌───────────┐ ┌──────────┐         ┌─────────────────┐
 │run_dbt_gol│ │sync_silv │         │archive_bronze_da│ (Lưu trữ nén JSON cũ)
 └─────┬─────┘ └─────┬────┘         └────────┬────────┘
       │             ▼                       │
       │       ┌──────────┐                  │
       │       │sync_postg│                  │
       │       └─────┬────┘                  │
       │             ▼                       │
       │       ┌──────────┐                  │
       │       │export_gol│                  │
       │       └─────┬────┘                  │
       ▼             ▼                       │
 ┌─────┴─────────────┴────┐                  │
 │  vacuum_delta_tables   │                  │ (Dọn dẹp file Delta cũ > 7 ngày)
 └───────────┬────────────┘                  │
             ▼                               ▼
       ┌───────────┐                   ┌───────────┐
       │    end    │                   │    end    │
       └───────────┘                   └───────────┘
```

---

## 4. Chi tiết các Tác vụ (Tasks) trong DAG

### 4.1. `crawl_all_sources` (PythonOperator)
* **Chức năng:** Thực thi script [run_scrapers.py](file:///d:/JobITVN/job_scraper_de_project/scripts/run_scrapers.py) qua `subprocess.Popen` để chạy song song các scrapers (`--workers 3`).
* **Bảo vệ an toàn:** Tự động kiểm tra file session cookie LinkedIn. Nếu chưa có session, tự động loại trừ LinkedIn (`--exclude linkedin`) để tránh bị block.
* **Đo lường (Metrics & XCom):** Đọc trực tiếp luồng stdout để phân tích số lượng bản ghi crawl thành công/thất bại của từng nguồn, sau đó đẩy thông tin (KPIs) lên XCom dưới dạng `scraper_metrics`.
* **Giới hạn thời gian (Timeout):** 5 giờ 15 phút (tránh treo vô hạn).

### 4.2. `run_dbt_staging` (BashOperator)
* **Chức năng:** Chạy lệnh `dbt run --select staging intermediate` để làm sạch, rename, cast type dữ liệu từ Bronze Delta Lake S3 vào DuckDB local.

### 4.3. `sync_silver_layer` (PythonOperator)
* **Chức năng:** Gọi Python Sync Engine (`SilverSyncEngine` và `JobDedupEngine`).
  1. Đọc dữ liệu từ DuckDB nạp vào PostgreSQL Silver schema (3NF).
  2. Thực hiện CDC Watermark checking (dựa trên `silver.cdc_watermarks`).
  3. Xử lý logic SCD Type 2 trên các tin thay đổi nội dung (`job_snapshots`).
  4. Thực hiện thuật toán Dedup trùng lặp cross-source (`JobDedupEngine`).
* **Thời gian chờ tối đa:** 30 phút.

### 4.4. `run_dbt_gold` (BashOperator)
* **Chức năng:** Chạy lệnh `dbt run --select marts --target duckdb_dev` để xây dựng mô hình Star Schema và các BI Data Marts trên DuckDB phục vụ Power BI.

### 4.5. `sync_postgres_gold` (PythonOperator)
* **Chức năng:** Gọi các Stored Procedures trên PostgreSQL để đồng bộ dữ liệu từ tầng Silver sang Gold DWH và refresh các views phục vụ Web:
  * `CALL dwh.sp_sync_dim_source();`
  * `CALL dwh.sp_sync_dim_company();`
  * `CALL dwh.sp_sync_fact_job_posting();`
  * `CALL dwh.sp_sync_skills_and_locations();`
  * `CALL dwh.sp_refresh_mart_api();` (refresh view `mart_api.latest_jobs_flat`)
  * `CALL dwh.sp_refresh_all_materialized_views();` (refresh các materialized views concurrently).

### 4.6. `export_gold_marts` (PythonOperator)
* **Chức năng:** Gọi `GoldExporter` kết nối PostgreSQL đọc dữ liệu Gold Marts và ghi đè Delta tables lên S3 (`s3://jobit-gold/gold/`) phục vụ ML.

### 4.7. `vacuum_delta_tables` (PythonOperator)
* **Chức năng:** Bảo trì các bảng Delta S3, gọi lệnh `VACUUM` để xóa bỏ lịch sử log và file Parquet cũ quá 7 ngày (`VACUUM_RETENTION_HOURS=168`).
* **Quy tắc kích hoạt (Trigger Rule):** `all_done` (vẫn chạy dọn dẹp ngay cả khi các bước export trước đó gặp lỗi).

### 4.8. `archive_bronze_data` (PythonOperator)
* **Chức năng:** Tối ưu dung lượng đĩa cứng local. Gọi module `bronze_archiver` gom nén toàn bộ các file JSON thô cũ quá 30 ngày thành Parquet nén ZSTD trên S3.
* **Quy tắc kích hoạt (Trigger Rule):** `all_done`.

---

## 5. Chiến lược Retry & An toàn

1. **Retry tự động:** Cấu hình mặc định của DAG có `retries = 1` và `retry_delay = 5 phút` đối với tất cả các tasks để tự động khắc phục các lỗi chập mạng tạm thời.
2. **Cách ly tài nguyên (Limits & Isolation):**
   * Container Airflow được giới hạn deploy tối đa `4.0 cpus` và `6G RAM` để không gây nghẽn máy host.
   * Cấu hình Airflow WebServer worker (`AIRFLOW__WEBSERVER__WORKERS: 1`) và Scheduler parsing processes giúp Airflow chạy cực kỳ nhẹ lúc nhàn rỗi (CPU gần 0%, RAM tiêu tốn ít).
