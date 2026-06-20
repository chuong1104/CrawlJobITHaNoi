# System Architecture: Local AWS Lakehouse

## Overview

JobITVN Data Platform được thiết kế theo kiến trúc **Local AWS Lakehouse**, ứng dụng mô hình Modern Data Stack hiện đại nhất. Mô hình này giả lập hoàn hảo môi trường AWS trên local bằng Floci, kết hợp sức mạnh xử lý phân tích siêu tốc của DuckDB và luồng chuyển đổi dữ liệu chuẩn chỉ của dbt.

Mục tiêu kiến trúc:

*   Xây dựng mô hình Cloud-Native (AWS) chạy hoàn toàn trên máy cá nhân mà không tốn chi phí.
*   Tách biệt hoàn toàn Storage (Floci S3) và Compute (DuckDB).
*   Áp dụng kiến trúc Medallion (Bronze, Silver, Gold) chuẩn Lakehouse.
*   Xử lý siêu nhẹ, tối ưu tài nguyên phần cứng.
*   Dễ dàng "bê nguyên xi" lên AWS thật (S3 + Athena/Redshift) trong tương lai.

---

# 1. High Level Architecture

```text
                    ┌─────────────────────┐
                    │  Job Websites       │
                    │---------------------│
                    │ ITviec, TopCV,      │
                    │ VietnamWorks, ...   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Crawling Layer      │
                    │ (Python/Playwright) │
                    └──────────┬──────────┘
                               │ (boto3)
                               ▼
        ┌───────────────────────────────────────────────┐
        │                AWS LOCAL CLOUD                │
        │                   (Floci)                     │
        │                                               │
        │   ┌───────────────────────────────────────┐   │
        │   │           Data Lake (S3)              │   │
        │   │                                       │   │
        │   │  [Bronze]   [Silver]      [Gold]      │   │
        │   │  (JSON)    (Parquet)     (Parquet)    │   │
        │   └───────────────────────────────────────┘   │
        └──────────────────────▲────────────────────────┘
                               │
                       (Read/Write S3)
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Compute & Transform│
                    │    (dbt + DuckDB)   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Data Mart Layer    │
                    │  (DuckDB Views)     │
                    └─────┬──────┬────────┘
                          │      │
              ┌───────────┘      └───────────┐
              ▼                              ▼
     Search & Recommendation         Analytics Layer
              │                              │
              ▼                              ▼
         FastAPI API                    Power BI
              │
              ▼
          Web Portal
```

---

# 2. Architectural Principles

## Data Lakehouse Paradigm
Lưu trữ toàn bộ dữ liệu (từ thô đến sạch) trên Object Storage (S3) dưới định dạng mở (JSON, Parquet). Dùng DuckDB như một Query Engine cắm trực tiếp vào S3 để phân tích mà không cần load dữ liệu vào một Database cục bộ nào.

## Separation of Storage and Compute
- **Storage:** Floci giả lập AWS S3. Nhẹ, lưu trữ không giới hạn.
- **Compute:** DuckDB và dbt. Chỉ hoạt động khi có câu lệnh query, không tốn RAM chạy nền duy trì Database.

## Medallion Architecture (Bronze - Silver - Gold)
Áp dụng chuẩn tổ chức dữ liệu của Databricks:
- **Bronze (Raw):** Dữ liệu JSON/HTML nguyên bản từ crawler.
- **Silver (Cleaned):** Dữ liệu đã làm sạch, chuẩn hóa kiểu dữ liệu, lưu dạng Parquet.
- **Gold (Aggregated):** Dữ liệu tổng hợp (Fact/Dim), tối ưu cho báo cáo BI.

## Metadata Driven & Idempotency
Pipeline (dbt) có thể chạy lại nhiều lần mà không tạo dữ liệu sai.

---

# 3. Service Architecture

```text
job-it-platform
│
├── crawler (Python)
├── airflow (Orchestration)
├── floci (Local AWS: S3, RDS)
├── dbt (Transformation)
├── duckdb (Compute Engine)
├── fastapi (Serving API)
└── powerbi (Visualization)
```

---

# 4. Crawling Layer

## Purpose
Thu thập dữ liệu từ các website tuyển dụng và đẩy thẳng lên Data Lake.

## Crawl Flow
```text
Website ──> Scraper (Playwright/Scrapy) ──> Python (boto3) ──> Floci S3 (Bronze Layer)
```

Thay vì ghi file ra ổ cứng local, scraper tương tác với Floci S3 y hệt như đang dùng Amazon S3 thật.

---

# 5. The Lakehouse: Floci S3 + DuckDB + dbt

Đây là lõi của hệ thống.

## 5.1 Tầng Storage: Floci S3
Tất cả dữ liệu nằm trong các bucket:
*   `s3://jobit-bronze`: Lưu file raw JSON/HTML theo từng ngày (`/YYYY/MM/DD/`).
*   `s3://jobit-silver`: Lưu bảng đã làm sạch dạng file `.parquet`.
*   `s3://jobit-gold`: Lưu mô hình Dimensional (Fact, Dim) dạng `.parquet`.

## 5.2 Tầng Compute: DuckDB
DuckDB đóng vai trò như AWS Athena. Nó dùng extension `httpfs` để kết nối vào `localhost:4566` (Floci) và đọc/ghi file Parquet siêu tốc bằng SQL.

## 5.3 Tầng Transformation: dbt (Data Build Tool)
dbt định nghĩa toàn bộ luồng biến đổi dữ liệu bằng SQL. Thay vì viết script Python/Pandas phức tạp, chúng ta viết dbt models:

1.  **Staging Models:** Đọc từ S3 Bronze, parse JSON, đổi tên cột.
2.  **Intermediate Models:** Dedup, xử lý logic nghiệp vụ.
3.  **Mart Models:** Build Fact/Dim tables, ghi ra S3 Gold.

---

# 6. Pipeline Layers (Medallion Flow)

## Bronze Layer (Raw)
*   **Định dạng:** JSON Lines (`.jsonl`), HTML.
*   **Trách nhiệm:** Lưu vết lịch sử gốc, không bao giờ sửa đổi.

## Silver Layer (Cleaned & Standardized)
*   **Định dạng:** Parquet (nén tốt, đọc theo cột cực nhanh).
*   **Nhiệm vụ:**
    *   Parse mức lương (min, max).
    *   Trích xuất kỹ năng (Skill Extraction).
    *   Lọc trùng lặp (Deduplication).
*   **Ví dụ dbt model:** `stg_topcv_jobs`, `int_deduped_jobs`.

## Gold Layer (Data Warehouse / Star Schema)
*   **Định dạng:** Parquet.
*   **Nhiệm vụ:** Phục vụ phân tích.
*   **Dimensions:** `dim_company`, `dim_skill`, `dim_location`, `dim_date`.
*   **Facts:** `fact_job_posting`.

---

# 7. Data Mart Layer & Serving

*   **BI Mart:** Power BI kết nối vào DuckDB file hoặc đọc file Parquet từ S3 Gold để lên báo cáo.
*   **API Mart:** FastAPI dùng thư viện `duckdb-python` để query các bảng/view Gold và trả kết quả cho Web Portal.

---

# 8. Airflow Orchestration

Airflow điều phối luồng chạy hàng ngày (Daily DAG):

```text
crawl_topcv ──────┐
crawl_itviec ─────┼──► dbt_run_staging ──► dbt_run_silver ──► dbt_run_gold ──► data_quality_check
crawl_linkedin ───┘
```

---

# 9. Deployment Architecture

## Docker Compose Services

```yaml
services:
  floci:       # Giả lập AWS (S3, IAM, ...)
  airflow:     # Điều phối
  crawler:     # Job thu thập dữ liệu
  dbt:         # Chạy dbt models
  api:         # FastAPI
```

---

# 10. Tại sao kiến trúc này tối ưu?

1.  **Cloud-Ready 100%:** Code Python dùng `boto3` và SQL của `dbt` không cần sửa một dòng nào nếu ngày mai dự án được chuyển lên AWS thật (chỉ cần đổi credentials).
2.  **Siêu nhẹ:** Bỏ đi PostgreSQL DWH nặng nề. Floci chỉ tốn 13MB RAM. DuckDB chạy In-Process không tốn RAM duy trì. Rất thân thiện với Laptop cá nhân.
3.  **Bắt kịp xu hướng:** Kiến trúc Data Lakehouse, dbt, và DuckDB là những kỹ năng được săn đón nhất trong mảng Data Engineering hiện tại.
