# Data Pipeline Design (ELT with dbt)

## Overview

Data Pipeline là trái tim của toàn bộ hệ thống. Trong kiến trúc **Local AWS Lakehouse**, chúng ta sử dụng mô hình **ELT** (Extract, Load, Transform) thay vì ETL truyền thống:

1. **Extract & Load (E & L):** Trình cào thu thập dữ liệu và "đổ" thẳng toàn bộ file JSON nguyên bản vào Data Lake (Floci S3 Bronze Layer).
2. **Transform (T):** Airflow kích hoạt `dbt` để đọc dữ liệu từ Bronze, biến đổi bằng DuckDB, và ghi lại xuống S3 dưới định dạng Parquet (Silver & Gold).

---

# 1. Complete End-to-End Data Pipeline

```text
┌─────────────────────────────────────────────┐
│               JOB WEBSITES                  │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│    CRAWLER LAYER (Python, Playwright)       │
└─────────────────────┬───────────────────────┘
                      │ Extract & Load
                      ▼
┌─────────────────────────────────────────────┐
│     BRONZE LAYER (Floci S3 - s3://bronze)   │
│         Raw Data (JSON, HTML)               │
└─────────────────────┬───────────────────────┘
                      │
      dbt run (DuckDB queries over HTTPFS)
                      │
                      ▼
┌─────────────────────────────────────────────┐
│    STAGING MODELS (dbt - Ephemeral/View)    │
│    - Rename columns                         │
│    - Cast data types                        │
│    - Parse Salary (Min, Max)                │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│     SILVER LAYER (Floci S3 - s3://silver)   │
│      Cleaned Data (Parquet)                 │
│    - Deduplication (Lọc trùng lặp)          │
│    - Skill Extraction (Trích xuất kỹ năng)  │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│      GOLD LAYER (Floci S3 - s3://gold)      │
│     Data Warehouse / Star Schema            │
│    - fact_job_posting (Parquet)             │
│    - dim_company (Parquet)                  │
│    - dim_skill, bridge_job_skill            │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│                 DATA MARTS                  │
│        (DuckDB Views trên Gold Parquet)     │
└───────┬────────────┬─────────────┬──────────┘
        │            │             │
        ▼            ▼             ▼
    Power BI     Search API   Recommendation
                       │
                       ▼
                   FastAPI
```

---

# 2. Các Bước Transformation (The "T" in ELT)

Biến đổi dữ liệu hoàn toàn do **dbt** chịu trách nhiệm. Quá trình này được chia thành các Models:

## 2.1 Staging Models (`stg_`)
- Đọc dữ liệu từ S3 Bronze (`read_json_auto`).
- Chuẩn hóa tên cột từ các nguồn khác nhau (ví dụ: `salary_text`, `salaryDisplay` đều quy về `raw_salary`).
- **Data Quality:** Loại bỏ các record thiếu `job_title` hoặc `company`.

## 2.2 Intermediate Models (`int_`)
Thực hiện các logic nghiệp vụ phức tạp trước khi nạp vào kho:
- **`int_salary_parsing`**: Dùng Regex trong SQL để tách `raw_salary` thành `salary_min` và `salary_max`.
- **`int_job_deduplication`**: 
  - Một Job đăng trên TopCV và ITviec có thể bị trùng.
  - dbt dùng hàm `QUALIFY ROW_NUMBER() OVER (PARTITION BY company, title ORDER BY date DESC) = 1` để giữ lại bản ghi mới nhất.
- **`int_skill_extraction`**: Dùng hàm LIKE/Regex để map các từ khóa trong `description` với bảng `seed_skills`.

## 2.3 Mart Models (`dim_`, `fct_`)
Đây là tầng Gold.
- **`dim_company`**: Chứa danh sách các công ty duy nhất. Sử dụng **dbt snapshots** để tạo cấu trúc SCD Type 2 (theo dõi lịch sử thay đổi thông tin công ty).
- **`fct_job_posting`**: Bảng trung tâm chứa thông tin về việc làm. Cấu hình dbt `materialized='incremental'` để chỉ xử lý các job mới được crawl ngày hôm nay thay vì chạy lại toàn bộ kho dữ liệu.

---

# 3. Incremental Processing Design

Không thể chạy lại (Full Refresh) hàng triệu Job mỗi ngày. dbt hỗ trợ **Incremental Models**:

```sql
{{ config(
    materialized='incremental',
    unique_key='job_id'
) }}

SELECT * 
FROM {{ ref('int_deduped_jobs') }}

{% if is_incremental() %}
  -- Chỉ lấy các job mới crawl trong ngày hôm nay
  WHERE crawl_date >= (SELECT max(crawl_date) FROM {{ this }})
{% endif %}
```

Khi Airflow gọi lệnh `dbt run`, DuckDB sẽ chỉ đọc file JSON của ngày hôm đó từ Bronze, xử lý và `APPEND` (hoặc `MERGE`) vào file Parquet ở tầng Silver/Gold.

---

# 4. Data Quality Checks (dbt tests)

Đảm bảo dữ liệu không bị rác khi đưa vào Data Warehouse. Cấu hình file `schema.yml` trong dbt:

```yaml
models:
  - name: fct_job_posting
    columns:
      - name: job_id
        tests:
          - unique
          - not_null
      - name: salary_min
        tests:
          - expression_is_true:
              expression: ">= 0"
```
Nếu test failed, Airflow sẽ báo đỏ (Alert) và dừng pipeline.

---

# 5. Airflow DAG (Daily Execution)

Airflow điều phối theo cơ chế Dependency rất rõ ràng:

```text
start_pipeline
      │
      ▼
crawl_topcv ──┐
crawl_itviec ─┼──► wait_for_crawlers_finish
crawl_jobsgo ─┘
      │
      ▼
dbt_source_freshness_check (Đảm bảo file S3 mới đã có)
      │
      ▼
dbt_run_staging (stg_ models)
      │
      ▼
dbt_run_intermediate (int_ models, dedup, parse)
      │
      ▼
dbt_run_marts (dim_, fct_ models, ghi Parquet ra Gold S3)
      │
      ▼
dbt_test (Chạy kiểm định chất lượng)
      │
      ▼
end_pipeline
```

---

# 6. Final Pipeline Summary

Với kiến trúc **Local AWS Lakehouse (Floci + DuckDB + dbt)**:
- **Tốc độ:** Rất nhanh nhờ Vectorized Execution của DuckDB và Parquet.
- **Tính trơn tru:** dbt xử lý mọi dependencies giữa các bảng (Ref).
- **Không có Data Silos:** Toàn bộ dữ liệu tập trung ở Floci S3.
- **Tiêu chuẩn công nghiệp:** Code dbt và Airflow này có thể được bê nguyên lên AWS (chạy dbt trên EMR/Glue/Athena) hoặc Databricks mà gần như không phải đập đi xây lại.
