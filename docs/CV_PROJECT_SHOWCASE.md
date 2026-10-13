# 🎯 JobITVN Data Platform: Career Showcase & Interview Cheat Sheet

> **Tài liệu hướng dẫn trình bày dự án JobITVN trong CV, hồ sơ LinkedIn và chuẩn bị phỏng vấn kỹ thuật cho vị trí Data Engineer / Analytics Engineer.**

---

## 📌 1. Tóm tắt dự án đưa vào CV (Project Summary)

### **JobITVN — Enterprise Medallion Lakehouse & Automated ELT Platform**
* **Vị trí / Vai trò:** Data Engineer (Lead Designer & Developer)
* **Ngăn xếp công nghệ:** Python, Apache Airflow, Delta Lake, DuckDB, dbt-core, PostgreSQL 17, Pydantic v2, Scrapling/Playwright, FastAPI, Docker, Power BI.
* **Mô tả ngắn gọn:** Xây dựng nền tảng Lakehouse phân tích thị trường tuyển dụng IT Việt Nam chuẩn Medallion Architecture (Bronze $\rightarrow$ Silver $\rightarrow$ Gold), tự động thu thập từ 8+ nền tảng (TopCV, ITviec, LinkedIn,...), tích hợp CDC Watermark, SCD Type 2, và tối ưu hóa tài nguyên phần cứng giảm 75% RAM footprint.

---

## 📝 2. Mẫu Bullet Points chuẩn Google XYZ / STAR Format

Bạn có thể tùy chỉnh các gạch đầu dòng dưới đây theo cấp bậc mong muốn:

### 💼 Dành cho vị trí Data Engineer (General / Mid-Level)
* **[Orchestration & Ingestion]:** Thiết kế và vận hành pipeline ELT tự động bằng **Apache Airflow 2.10**, thu thập và chuẩn hóa dữ liệu việc làm từ **8+ nền tảng tuyển dụng** sử dụng **Pydantic Data Contracts**, kiểm soát 100% schema validation trước khi nạp vào Lakehouse.
* **[Storage & ACID]:** Triển khai lớp **Bronze Lakehouse** trên **Delta Lake (S3)** với giao dịch ACID và cơ chế partition động theo ngày, tích hợp tác vụ `VACUUM` định kỳ giúp giải phóng dung lượng đĩa và ngăn ngừa data corruption.
* **[Change Data Capture & Lifecycle]:** Xây dựng **Watermark CDC Engine** kết hợp cơ chế băm kép (`identity_hash` & `content_hash`), giúp **cắt giảm 85–90% lượng ghi I/O dư thừa** vào PostgreSQL ODS và duy trì lịch sử biến động lương/deadline bằng **SCD Type 2**.
* **[Resource Optimization]:** Tinh chỉnh cấu hình tài nguyên toàn bộ hệ thống (Airflow, Postgres shared_buffers, DuckDB memory limit, Scrapling TLS) giúp toàn bộ nền tảng vận hành mượt mà với chỉ **~1.5GB RAM** (tiết kiệm 75% so với cấu hình mặc định ~6GB).

### 📊 Dành cho vị trí Analytics Engineer / BI Engineer
* **[Data Modeling]:** Xây dựng mô hình dữ liệu đa tầng gồm **Silver ODS chuẩn 3NF** và **Gold DWH chuẩn Kimball (Star Schema)** với Fact (`fct_job_posting`) và các Dimensions, Bridge tables hỗ trợ quan hệ nhiều-nhiều (kỹ năng, địa điểm).
* **[Transformation & dbt]:** Phát triển **15+ models dbt-core** kết hợp In-Memory OLAP engine **DuckDB** để làm sạch, chuẩn hóa kỹ năng và bóc tách mức lương đa định dạng với tốc độ xử lý hàng trăm nghìn dòng dữ liệu chỉ trong vài giây.
* **[Serving & Dashboard]:** Thiết kế **Materialized Views** tối ưu hóa truy vấn serving qua **FastAPI REST API** (<50ms response time) và kết nối trực tiếp với **Power BI Desktop** (DirectQuery/Star Schema) để trực quan hóa xu hướng công nghệ và mức lương theo thời gian thực.

---

## 🎤 3. Bộ câu hỏi phỏng vấn kỹ thuật & Đáp án mẫu (Technical Interview Q&A)

### ❓ Câu 1: Tại sao bạn chọn DuckDB + dbt thay vì Apache Spark cho tầng Transformation?
> **Trả lời:**  
> "Trong dự án này, bài toán đặt ra là cần xử lý hàng trăm nghìn đến hàng triệu bản ghi việc làm định kỳ mỗi ngày trên môi trường máy chủ tối ưu chi phí (hoặc local machine). Cụm Apache Spark đòi hỏi tài nguyên rất lớn (ít nhất 4GB–8GB RAM chỉ để dựng Driver & Executor) và độ trễ khởi động JVM đáng kể.  
> Thay vào đó, tôi chọn **DuckDB** kết hợp **dbt-core**: DuckDB là một In-Memory Columnar OLAP Engine viết bằng C++, có khả năng đọc trực tiếp Delta Tables trên S3 qua hàm `delta_scan()` với cơ chế vectorization siêu nhanh và footprint bộ nhớ dưới 200MB. Khi dữ liệu scale lên hàng chục terabytes trong môi trường doanh nghiệp lớn, toàn bộ logic SQL trong dbt models hoàn toàn có thể tái sử dụng để chuyển đổi sang Databricks Spark hoặc Snowflake mà không cần viết lại nghiệp vụ."

---

### ❓ Câu 2: Cơ chế Watermark CDC và SCD Type 2 trong hệ thống hoạt động như thế nào?
> **Trả lời:**  
> "Để tránh tình trạng nạp lại toàn bộ dữ liệu (Full Refresh) gây nghẽn database, tôi thiết kế cơ chế **CDC Watermark**:
> 1. Hệ thống lưu mốc `last_sync_at` cho từng nguồn crawl trong bảng `silver.cdc_watermarks`. Lần chạy sau chỉ quét dữ liệu có `scraped_at > last_sync_at`.
> 2. Tôi sử dụng 2 giá trị băm:
>    * `identity_hash`: Tạo từ (nguồn, công ty, địa điểm, chức danh) để xác định định danh duy nhất của công việc.
>    * `content_hash`: Tạo từ (mô tả, mức lương, yêu cầu, hạn nộp) để phát hiện sự thay đổi nội dung.
> 3. Khi `identity_hash` đã tồn tại nhưng `content_hash` thay đổi, hệ thống kích hoạt logic **SCD Type 2**: cập nhật bản ghi cũ `valid_to = NOW()`, `is_current = false`, và nạp bản ghi mới với `valid_from = NOW()`, `is_current = true`, ghi nhận lý do thay đổi (`SALARY_CHANGE`, `DEADLINE_EXTENDED`,...). Nhờ đó, chúng tôi bảo toàn 100% lịch sử biến động thị trường tuyển dụng."

---

### ❓ Câu 3: Làm thế nào để giải quyết bài toán trùng lặp tên công ty (Fuzzy Entity Resolution)?
> **Trả lời:**  
> "Tên công ty trên các trang tuyển dụng thường không đồng nhất, ví dụ: 'FPT Software', 'Công ty TNHH Phần mềm FPT', 'FPT Software Co., Ltd'.  
> Tôi giải quyết bài toán này ở tầng **PostgreSQL Silver** bằng cách:
> 1. Chuẩn hóa chuỗi (bỏ dấu tiếng Việt bằng extension `unaccent`, chuyển chữ thường, loại bỏ các tiền tố pháp lý thông dụng như 'công ty', 'tnhh', 'jsc').
> 2. Sử dụng extension **`pg_trgm` (Trigram Similarity)** kết hợp chỉ mục GiST/GIN để tính toán độ tương đồng chuỗi.
> 3. Thiết lập ngưỡng tin cậy (similarity threshold > 0.85). Nếu độ tương đồng vượt ngưỡng, bản ghi sẽ được tự động gán vào `company_id` hiện có, ngăn ngừa tình trạng phân mảnh dimension bảng công ty."

---

### ❓ Câu 4: Bạn đã áp dụng những kỹ thuật nào để giảm RAM từ ~6GB xuống ~1.5GB?
> **Trả lời:**  
> "Tôi thực hiện tối ưu hóa toàn diện trên cả 4 tầng:
> 1. **Ingestion Layer:** Cắt giảm việc dùng Playwright/Chromium (vốn chiếm 300MB–500MB/worker) sang **Scrapling HTTP** giả lập TLS/JA4 fingerprint (chỉ tốn ~30MB/process). Chỉ giữ Playwright cho LinkedIn với cơ chế tái sử dụng Cookie session.
> 2. **Database:** Tinh chỉnh PostgreSQL với `shared_buffers = 128MB` và `work_mem = 8MB`, vừa đủ cho các truy vấn đánh chỉ mục mà không chiếm dụng bộ nhớ đệm hệ thống.
> 3. **Orchestrator:** Giảm số worker của Airflow Webserver về 1 (dùng gevent worker class), giới hạn `parsing_processes = 1` và tăng chu kỳ quét DAGs từ 30s lên 60s.
> 4. **Compute Engine:** Thiết lập giới hạn `max_memory` cho DuckDB để tận dụng cơ chế Out-of-core execution (ghi tạm ra đĩa khi bộ nhớ đạt ngưỡng) thay vì gây Out-Of-Memory."

---

## 🚀 4. Điểm nhấn kiến trúc so với dự án thông thường
| Tiêu chí | Dự án DE thông thường | Dự án JobITVN |
|---|---|---|
| **Lưu trữ dữ liệu** | Ghi file CSV/JSON đơn thuần vào thư mục | **Delta Lake (ACID Log, Time-Travel, Partitioning, VACUUM)** |
| **Kiểm soát chất lượng** | Xử lý lỗi sau khi đã nạp vào DB | **Pydantic Data Contracts chặn lỗi ngay tại Gateway Ingestion** |
| **Mô hình hóa dữ liệu** | Gom tất cả vào 1-2 bảng phẳng lớn | **Medallion 3 tầng: Bronze (Delta) $\rightarrow$ Silver (3NF ODS) $\rightarrow$ Gold (Kimball Star Schema)** |
| **Đồng bộ dữ liệu** | Chạy TRUNCATE & INSERT toàn bộ (Full Load) | **Watermark CDC + SCD Type 2 (giảm 90% tải ghi)** |
| **Hiệu năng serving** | Chọc trực tiếp vào bảng thô | **Materialized Views + Connection Pool + TTL Caching (<50ms)** |
