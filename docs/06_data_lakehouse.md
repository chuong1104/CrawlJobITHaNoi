# Data Lakehouse Design (Medallion Architecture)

## Overview

JobITVN áp dụng kiến trúc **Data Lakehouse** hiện đại để quản lý dữ liệu. Thay vì lưu trữ tệp phẳng đơn thuần, chúng ta lưu trữ dữ liệu dưới định dạng **Delta Lake (Open Table Format)** trên Object Storage (S3/Floci) và sử dụng DuckDB + dbt + PostgreSQL để biến đổi, quản lý ACID Transactions, Time Travel, và phục vụ phân tích hiệu năng cao.

Luồng dữ liệu được chia làm 3 tầng theo **Medallion Architecture** nâng cấp:
- **Bronze (Raw Table):** Dữ liệu thô nguyên bản được lưu dưới dạng **Delta Table** trên S3, hỗ trợ Time Travel và Schema Evolution.
- **Silver (Operational 3NF):** Dữ liệu được làm sạch, chuẩn hóa và lưu trữ có cấu trúc chuẩn 3NF trong **PostgreSQL** để duy trì tính toàn vẹn nghiệp vụ, xử lý SCD Type 2 lịch sử trạng thái job và thực hiện CDC (Change Data Capture) dựa trên Watermark.
- **Gold (Data Warehouse & Marts):** Dữ liệu tổng hợp (Fact/Dim) được tổ chức theo Kimball Dimensional Model trong PostgreSQL (tối ưu bằng Materialized Views) đồng thời được xuất ngược ra S3 dưới dạng **Delta Table** (mart_bi, mart_ml) để phục vụ các phân tích nâng cao, ML, và Power BI.

---

# 1. Why Delta Lake & Data Lakehouse?

## Khuyết điểm của định dạng Parquet "raw" truyền thống
- Thiếu tính năng giao dịch (ACID): Khi pipeline bị ngắt giữa chừng, file Parquet có thể bị hỏng (corrupt).
- Không có lịch sử phiên bản (Time Travel): Khó truy vấn lại dữ liệu tại một thời điểm trong quá khứ để debug hoặc train ML model.
- Schema Drift: Khó quản lý khi các trang tuyển dụng thay đổi cấu trúc/thêm cột.

## Ưu điểm của kiến trúc Delta Lake (via python-deltalake & DuckDB)
- **ACID Transactions:** Đảm bảo toàn vẹn dữ liệu cho Data Lake, không có tình trạng file hỏng.
- **Time Travel:** Hỗ trợ đọc dữ liệu tại bất kỳ version nào thông qua lịch sử commits (ví dụ: `read_delta_table(version=5)`).
- **Schema Evolution:** Tự động gộp schema mới (schema merge) khi scraper thu thập thêm trường thông tin mà không làm lỗi pipeline.
- **DuckDB Native Integration:** DuckDB truy vấn trực tiếp Delta Table qua extension `delta` bằng hàm `delta_scan()`.
- **Separation of Compute & Storage:** Toàn bộ compute do DuckDB & PostgreSQL engine gánh trên RAM/CPU, storage nằm hoàn toàn trên Floci S3.

---

# 2. Bronze Layer (Tầng thô - Delta Lake)

## Mục đích
Lưu trữ mọi thứ thu thập được từ các scrapers ở dạng nguyên bản nhất dưới dạng Delta Table. Đây là "Single Source of Truth" gốc rễ của hồ dữ liệu. Mọi thay đổi schema của nguồn tuyển dụng đều được Delta Lake tự động merge.

## Lưu trữ
- **Định dạng:** Delta Format (Parquet + Transaction Log `_delta_log`)
- **Vị trí:** `s3://jobit-bronze/bronze/{source}/`
- **Cơ chế Partition:** Phân vùng theo `_batch_date` để tối ưu filter pushdown.
- **Maintenance:** Chạy task `VACUUM` hàng tuần để dọn dẹp các tệp tin cũ quá 7 ngày, giúp tối ưu hóa không gian lưu trữ S3.

---

# 3. Silver Layer (Tầng chuẩn hóa - PostgreSQL 3NF & CDC)

## Mục đích
Làm sạch, chuẩn hóa kiểu dữ liệu, giải quyết trùng lặp thực thể (Entity Resolution - Aliases) và đồng bộ vào hệ quản trị cơ sở dữ liệu quan hệ PostgreSQL chuẩn hóa dạng 3NF (`jobs`, `companies`, `job_snapshots`).

## Quá trình biến đổi & Đồng bộ (CDC Watermark)
1. **Làm sạch dbt (Staging DuckDB):** dbt sử dụng DuckDB đọc trực tiếp từ Delta Bronze trên S3 qua `delta_scan()`, làm sạch chuỗi, chuẩn hóa mức lương, kỹ năng, và ngày tháng.
2. **CDC Delta-Load dựa trên Watermark:** `CDCWatermarkTracker` lưu lại thời điểm đồng bộ thành công cuối cùng của từng source trong bảng `silver.cdc_watermarks`. Lần chạy tiếp theo chỉ lấy các bản ghi có `scraped_at > last_sync_at`, giảm 80-90% lượng dữ liệu cần xử lý.
3. **SCD Type 2 (PostgreSQL):** Khi dữ liệu tin tuyển dụng có thay đổi (`content_hash` đổi), trigger/stored procedure trong PostgreSQL tự động đóng phiên bản cũ và tạo phiên bản mới trong bảng `silver.job_snapshots` (`is_current`, `valid_from`, `valid_to`).
4. **Fuzzy Dedup (Entity Resolution):** Sử dụng pg_trgm (Trigram Index) để map hàng chục bí danh công ty viết sai/viết tắt về một ID công ty chuẩn duy nhất.

---

# 4. Gold Layer (Tầng phân tích / Data Warehouse & Marts)

## Mục đích
Tổ chức dữ liệu theo **Star Schema** phục vụ trực tiếp cho báo cáo Power BI, API Serving (FastAPI), và Machine Learning.

## Lưu trữ & Phục vụ dữ liệu song song (Hybrid)
1. **PostgreSQL DWH Schema (`dwh`):** Lưu trữ Fact và Dimensions phục vụ cho các truy vấn của API. Được tối ưu hóa bằng **Materialized Views** refresh concurrently (`mv_active_jobs_summary`, `mv_kpi_realtime`).
2. **Delta Lake Marts (S3):** Xuất ngược dữ liệu từ PostgreSQL DWH ra S3 dưới dạng Delta Tables (`mart_bi`, `mart_ml`) thông qua `GoldExporter` phục vụ cho ML training và Power BI.

---

# 5. Các bảng quan trọng trong Gold Layer

## 5.1. dwh.fct_job_posting
Bảng Fact chính chứa các khóa ngoại tới Dimensions và các metrics đã chuẩn hóa.
```sql
-- fct_job_posting.sql
SELECT
    job_id,
    source_id,
    company_id,
    first_seen_date_key,
    last_seen_date_key,
    salary_avg,
    job_level,
    work_mode,
    is_active
FROM marts.warehouse.fct_job_posting
```

## 5.2. dwh.mv_active_jobs_summary (Materialized View)
Cache phi chuẩn hóa (denormalized) của tất cả job đang hoạt động kết hợp với thông tin công ty để phục vụ API FastAPI với thời gian phản hồi < 100ms.
```sql
CREATE MATERIALIZED VIEW dwh.mv_active_jobs_summary AS
SELECT f.job_id, f.title_clean, f.salary_avg, c.display_name AS company_name
FROM dwh.fct_job_posting f
JOIN dwh.dim_company c ON f.company_key = c.company_key
WHERE f.is_active = TRUE;
```

## 5.3. dbt Semantic Layer (Metrics Layer)
Định nghĩa tập trung 13 metrics nghiệp vụ quan trọng nhất tại `models/metrics/sem_job_market.yml` để đảm bảo tính nhất quán (Single Source of Truth) giữa các báo cáo.

---

# 6. Pipeline thực thi (với dbt-duckdb & Delta Lake)

Khi Airflow kích hoạt pipeline hàng ngày:
1. **Extract & Load:** Scrapers cào dữ liệu thô và gọi `BronzeManager` ghi trực tiếp vào Delta Lake trên S3.
2. **dbt Transform:** dbt Core load extension `delta` và compile các câu lệnh:
   ```sql
   -- dbt staging đọc Delta Lake qua delta_scan
   SELECT * FROM delta_scan('s3://jobit-bronze/bronze/topcv/')
   ```
3. **Sync Silver & Gold:** Python Sync Engine đồng bộ delta vào PostgreSQL Silver (CDC Watermark) và chạy stored procedures để cập nhật Gold DWH và refresh các Materialized Views.
4. **Gold Export:** `GoldExporter` đọc DWH và ghi ra Delta tables trên S3 (`s3://jobit-gold/gold/mart_bi/`).
5. **Vacuum:** Chạy `VACUUM` dọn dẹp các tệp tin log và tệp tin Parquet thừa của Delta tables trên S3.
