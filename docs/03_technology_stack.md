# Technology Stack

## Overview

JobITVN Data Platform được thiết kế theo nguyên tắc:

* Đơn giản nhưng tiệm cận với môi trường Enterprise Cloud.
* Dễ chạy trên máy cá nhân (siêu nhẹ, ít tốn RAM).
* Có thể bê nguyên xi (drop-in replacement) lên Production Cloud (AWS).
* Tập trung vào các kỹ năng Data Engineering cốt lõi: Data Lakehouse, dbt, Cloud Storage.

Thay vì dùng các công cụ Big Data cồng kềnh (Hadoop, Spark, Trino), dự án chọn stack "Modern Data Stack" hiện đại, thực dụng và được tích hợp các chuẩn doanh nghiệp.

---

# 1. Technology Stack Overview

| Layer                  | Technology | Vai trò & Đặc tả |
| :--------------------- | :--------------------------------- | :---------------- |
| **Crawling & Ingestion** | Scrapling (curl_cffi), Playwright, Pydantic v2 | 8+ portals; TLS/JA4 bypass (~30-50MB RAM/worker), Cookie session persistence (LinkedIn) |
| **Local Cloud Simulation** | Floci (giả lập AWS S3, Hybrid Storage) | S3 Object Storage mock cực nhẹ (khởi động 24ms, ~13MB RAM) |
| **Data Lake Storage** | **Delta Lake 0.18+ (python-deltalake)** trên S3 Floci | Bronze & Gold Delta Tables với ACID transactions (`_delta_log`), Time-Travel, VACUUM |
| **Operational ODS (Silver)** | **PostgreSQL 17 (3NF ODS)** | Ràng buộc 3NF, SCD Type 2 (`job_snapshots`), Watermark CDC, Trigram (`pg_trgm`) |
| **Data Warehouse (Gold)** | **PostgreSQL 17 & DuckDB 1.1+** | Kimball Star Schema (`dwh`), Materialized Views, In-Memory OLAP Columnar Engine |
| **Data Transformation** | dbt-core 1.8+ (dbt-duckdb, dbt-postgres) | 8 Staging models, 5 Intermediate models, 10 Warehouse & Mart models, data tests |
| **Semantic / Metrics Layer** | **dbt Semantic Layer (MetricFlow)** | Định nghĩa tập trung metrics thị trường (`sem_job_market.yml`), time-spine |
| **Orchestration** | Apache Airflow 2.10 (LocalExecutor) | Daily DAG `@ 06:00 AM`, parallel branch execution, XCom metrics (yêu cầu Docker ~4GB RAM) |
| **Serving API & Portal** | FastAPI 0.110+ + HTML5/CSS3 Dark Mode | SQLAlchemy QueuePool (5/10), TTL Cache in-memory, response time <50ms, Vercel ready |
| **Business Intelligence** | Power BI Desktop | DirectQuery vào PostgreSQL DWH hoặc ODBC vào DuckDB Star Schema |
| **Containerization & Ops** | Docker & Docker Compose v2 | Giới hạn 3 CPU, 4GB RAM container limit; tổng stack yêu cầu 4GB - 6GB RAM (kèm tài liệu chiến lược tối ưu RAM) |

---

# 2. Programming Language

## Python

### Purpose
Ngôn ngữ chính cho toàn bộ hệ thống.
Sử dụng trong: Crawling, Airflow DAG, dbt orchestration, API và các module đồng bộ (Sync Engine).

---

# 3. Local Cloud Simulation

## Floci

### Purpose
Giả lập toàn bộ môi trường đám mây AWS ngay trên máy tính cá nhân.
Floci tương tự LocalStack nhưng cực kỳ tối ưu: khởi động nhanh (24ms) và chỉ tốn 13MB RAM. Code dùng `boto3` cắm vào Floci y hệt như cắm vào AWS thật.

---

# 4. Storage Layer: The Delta Data Lake

## Delta Lake (Open Table Format) trên Floci S3

### Purpose
Lưu trữ dữ liệu thô (Bronze) và dữ liệu marts phân tích (Gold) dưới dạng **Delta Tables** thay vì các file phẳng Parquet đơn thuần.

### Tại sao lại là Delta Lake?
- **python-deltalake:** Sử dụng binding Python của Rust Delta engine, cho phép đọc/ghi Delta Table trực tiếp mà không cần cài Hadoop/Spark cồng kềnh.
- **ACID & Time Travel:** Đảm bảo quá trình ghi không bao giờ bị lỗi nửa chừng gây hỏng file, cho phép truy cập lại lịch sử dữ liệu tại bất kỳ thời điểm nào.
- **Phân lớp dữ liệu (Medallion Architecture):**
  * **Bronze Bucket:** Lưu dữ liệu raw Delta Table phân vùng theo `_batch_date` và tự động gộp schema (schema evolution).
  * **Gold Bucket:** Lưu dữ liệu marts Delta Table (`mart_bi`, `mart_ml`) phục vụ trực tiếp cho Power BI và AI/ML training.

---

# 5. Operational Database Layer (Tầng nghiệp vụ)

## PostgreSQL (Silver Layer ODS)

### Purpose
Lưu trữ dữ liệu chuẩn hóa dạng 3NF để xử lý lịch sử trạng thái của tin tuyển dụng (SCD Type 2) và giải quyết trùng lặp thực thể.

### Tại sao cần PostgreSQL ở Silver Layer?
Kiến trúc Lakehouse phẳng (Parquet files) khó thực thi triệt để các ràng buộc khóa ngoại (Foreign Keys) và logic fuzzy match. PostgreSQL đóng vai trò là ODS để thực hiện:
- **pg_trgm (Trigram Index):** Tìm kiếm mờ (fuzzy search) để gom nhiều alias của công ty về một ID duy nhất.
- **SCD Type 2:** Theo dõi lịch sử thay đổi thông tin tin tuyển dụng (lương, deadline).
- **CDC Watermark:** Tracking tiến độ sync thông qua bảng `silver.cdc_watermarks` giúp giảm tải và phát hiện anomaly.

---

# 6. Compute Engine & Serving

## DuckDB & PostgreSQL Materialized Views

- **DuckDB:** analytical engine in-process siêu tốc, tích hợp S3 (qua `httpfs`) để quét trực tiếp các Delta tables mà không cần nạp vào RAM.
- **PostgreSQL Materialized Views:** Lưu trữ cache tối ưu các câu truy vấn phức tạp của API và Power BI (như `mv_active_jobs_summary`, `mv_kpi_realtime`). Cấu hình refresh concurrently hàng ngày.

---

# 7. Data Transformation & Semantic Layer

## dbt (Data Build Tool) & dbt Semantic Layer

- **dbt Core:** Thực hiện transform dữ liệu và quản lý dependencies của các models.
- **dbt Semantic Layer:** Định nghĩa tập trung các KPI (lương trung bình, tổng job, tỷ lệ fresher) trong file YAML. Đảm bảo tính nhất quán (Single Source of Truth) giữa các dashboard và API.
