# Technology Stack

## Overview

JobITVN Data Platform được thiết kế theo nguyên tắc:

* Đơn giản nhưng tiệm cận với môi trường Enterprise Cloud.
* Dễ chạy trên máy cá nhân (siêu nhẹ, ít tốn RAM).
* Có thể bê nguyên xi (drop-in replacement) lên Production Cloud (AWS).
* Tập trung vào kỹ năng Data Engineering cốt lõi: Data Lakehouse, dbt, Cloud Storage.

Thay vì dùng các công cụ Big Data cồng kềnh (Hadoop, Spark, Trino), dự án chọn stack "Modern Data Stack" hiện đại và thực dụng nhất.

---

# 1. Technology Stack Overview

| Layer                  | Technology                        |
| ---------------------- | --------------------------------- |
| Crawling               | Scrapy, Playwright, Python        |
| Local Cloud Simulation | Floci (giả lập AWS S3, RDS)       |
| Data Lake Storage      | Floci S3 (thay thế MinIO/S3 thật) |
| Compute Engine         | DuckDB                            |
| Data Transformation    | dbt-core (dbt-duckdb)             |
| Orchestration          | Apache Airflow                    |
| Serving API            | FastAPI                           |
| Dashboard              | Power BI                          |
| Containerization       | Docker                            |

---

# 2. Programming Language

## Python

### Purpose
Ngôn ngữ chính cho toàn bộ hệ thống.
Sử dụng trong: Crawling, Airflow DAG, dbt orchestration, API.

### Why Python
Python hiện là ngôn ngữ phổ biến nhất trong Data Engineering. Có hệ sinh thái cực mạnh: `boto3` (AWS), `duckdb-python`, `fastapi`, `playwright`.

---

# 3. Local Cloud Simulation

## Floci

### Purpose
Giả lập toàn bộ môi trường đám mây AWS ngay trên máy tính cá nhân.

### Tại sao lại là Floci?
Floci là một Local Cloud Emulator tương tự LocalStack nhưng cực kỳ tối ưu:
- **Tốc độ:** Khởi động trong 24ms.
- **Tiết kiệm:** Chỉ tốn 13MB RAM khi chạy nền (cực kỳ phù hợp cho môi trường local).
- **Chuẩn xác:** Hỗ trợ giao thức của AWS S3, RDS, IAM hoàn hảo. Code dùng `boto3` cắm vào Floci y hệt như cắm vào AWS thật. Không cần sửa code khi đưa lên Production.

---

# 4. Storage Layer: The Data Lake

## Floci S3 (Amazon S3)

### Purpose
Lưu trữ toàn bộ dữ liệu của dự án dưới dạng Object Storage thay vì Database truyền thống.

### Phân lớp dữ liệu (Medallion Architecture)
* **Bronze Bucket:** Lưu file JSON/HTML gốc thu được từ Crawler.
* **Silver Bucket:** Lưu file Parquet đã làm sạch.
* **Gold Bucket:** Lưu file Parquet đã tổng hợp thành mô hình Fact/Dim.

### Tại sao không dùng Database (như PostgreSQL) để lưu Raw Data?
Lưu file trên S3 rẻ hơn, không giới hạn dung lượng, dễ dàng tái xử lý (reprocessing) và là tiêu chuẩn của kiến trúc Data Lakehouse.

---

# 5. Compute Engine

## DuckDB

### Purpose
Đóng vai trò là cỗ máy phân tích (Analytical Engine) xử lý hàng triệu dòng dữ liệu siêu tốc.

### Tại sao lại là DuckDB?
DuckDB giống như "SQLite cho Data Analytics".
* **Không cần cài đặt Server:** Nó chạy in-process, không tiêu tốn RAM duy trì.
* **Tích hợp S3 tuyệt vời:** DuckDB có thể dùng thư viện `httpfs` để quét và truy vấn trực tiếp hàng loạt file `.parquet` nằm trên Floci S3 mà không cần nạp dữ liệu vào ổ cứng.
* **Nhanh:** Kiến trúc Columnar (dạng cột) và Vectorized giúp nó chạy các lệnh GROUP BY, JOIN cực kỳ nhanh.

### Why Not Spark / Trino?
Spark và Trino quá cồng kềnh cho một lượng dữ liệu dưới vài trăm GB. Chạy Spark trên local sẽ tiêu tốn rất nhiều RAM (thường là 8GB+ chỉ để nhàn rỗi), là sự "giết gà dùng dao mổ trâu" (over-engineering).

---

# 6. Data Transformation

## dbt (Data Build Tool)

### Purpose
Thực hiện toàn bộ logic biến đổi dữ liệu (ETL/ELT) từ Bronze -> Silver -> Gold.

### Tại sao lại là dbt?
dbt là tiêu chuẩn vàng của Data Engineering hiện tại.
* **Chỉ cần biết SQL:** Mọi logic làm sạch, parse lương, lọc trùng lặp đều được viết bằng SQL. dbt tự động biên dịch và bảo DuckDB thực thi.
* **Quản lý Dependencies:** Tự động xây dựng đồ thị DAG để biết bảng nào cần chạy trước, bảng nào chạy sau.
* **Kiểm thử dữ liệu (Data Testing):** Tích hợp sẵn tính năng test (ví dụ: cột không được NULL, dữ liệu phải là duy nhất).

---

# 7. Orchestration

## Apache Airflow

### Purpose
Điều phối toàn bộ vòng đời pipeline. Lên lịch chạy hàng ngày.

### Flow chính
Airflow sẽ kích hoạt Crawler (chạy Python) -> Đợi Crawler ghi file lên S3 -> Kích hoạt lệnh `dbt run` để DuckDB biến đổi dữ liệu -> Hoàn thành.

---

# 8. Crawling Layer

## Scrapy & Playwright

### Purpose
Thu thập dữ liệu từ các website. Scrapy dùng cho các trang tĩnh (TopCV, CareerLink), Playwright dùng cho các trang render bằng JavaScript (Glints, LinkedIn).

---

# 9. API & Serving

## FastAPI

### Purpose
Cung cấp dữ liệu cho Web Portal hoặc ứng dụng bên thứ 3.

### Cách hoạt động
FastAPI dùng thư viện `duckdb-python` kết nối trực tiếp vào các file Parquet Gold Layer trên S3 (hoặc DuckDB file) để truy vấn và trả về JSON cho Frontend. Rất nhẹ và nhanh.

---

# 10. Technology Decisions Summary

| Component            | Selected Tool          | Reason                                          |
| -------------------- | ---------------------- | ----------------------------------------------- |
| **Cloud Emulator**   | **Floci**              | Siêu nhẹ (13MB RAM), giả lập AWS chuẩn xác.     |
| **Data Lake**        | **Floci S3**           | Lưu trữ file gốc (Raw), tương thích AWS S3.     |
| **Data Warehouse**   | **DuckDB**             | Phân tích file trực tiếp siêu nhanh, ko cần Server|
| **Transformation**   | **dbt-core**           | Quản lý SQL logic chuẩn Enterprise.             |
| **Crawl JS Sites**   | **Playwright**         | Tốt hơn, nhẹ hơn Selenium.                      |
| **Orchestration**    | **Apache Airflow**     | Tiêu chuẩn của ngành Data.                      |
