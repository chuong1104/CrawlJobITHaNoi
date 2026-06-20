# Data Lakehouse Design (Medallion Architecture)

## Overview

JobITVN áp dụng kiến trúc **Data Lakehouse** hiện đại để quản lý dữ liệu. Thay vì nạp toàn bộ dữ liệu vào một Data Warehouse truyền thống (như PostgreSQL), chúng ta giữ nguyên dữ liệu trên Object Storage (S3/Floci) và sử dụng DuckDB + dbt để biến đổi và truy vấn trực tiếp.

Luồng dữ liệu được chia làm 3 tầng theo **Medallion Architecture** (chuẩn của Databricks):
- **Bronze (Raw):** Dữ liệu thô nguyên bản.
- **Silver (Staging & Cleansed):** Dữ liệu đã làm sạch, chuẩn hóa.
- **Gold (Data Warehouse/Marts):** Dữ liệu tổng hợp (Fact/Dim) phục vụ báo cáo.

---

# 1. Why Data Lakehouse?

## Khuyết điểm của Data Warehouse truyền thống (PostgreSQL DWH)
- Phải tạo bảng (schema) trước khi đưa dữ liệu vào.
- Data thô (JSON, HTML) khó lưu trữ tối ưu trong DB quan hệ.
- Tốn kém chi phí lưu trữ (Storage) và tính toán (Compute) vì chúng gắn chặt với nhau.

## Ưu điểm của Local AWS Lakehouse (Floci S3 + DuckDB)
- **Separation of Compute and Storage:** Dữ liệu nằm ở S3 (rẻ, không giới hạn). Compute do DuckDB thực thi (chỉ tốn CPU khi chạy query, cực kỳ nhanh).
- **Flexibility:** Xử lý tốt cả dữ liệu phi cấu trúc (HTML), bán cấu trúc (JSON) và có cấu trúc (Parquet).
- **Hiệu năng:** Định dạng Parquet kết hợp với công cụ Vectorized Execution của DuckDB giúp các truy vấn báo cáo nhanh gấp hàng chục lần so với PostgreSQL.

---

# 2. Bronze Layer (Tầng thô)

## Mục đích
Lưu trữ mọi thứ thu thập được từ website ở dạng nguyên bản nhất, không chỉnh sửa, không gọt giũa. Đây là "Single Source of Truth" gốc rễ. Đề phòng trường hợp logic parser ở các bước sau bị sai, chúng ta luôn có thể chạy lại từ đầu.

## Lưu trữ
- **Định dạng:** `.jsonl` (JSON Lines), `.html`
- **Vị trí:** `s3://jobit-bronze/`
- **Cấu trúc thư mục:**
  ```text
  s3://jobit-bronze/source=topcv/year=2026/month=06/day=20/data.jsonl
  ```

---

# 3. Silver Layer (Tầng làm sạch)

## Mục đích
Làm sạch, chuẩn hóa kiểu dữ liệu, giải quyết trùng lặp (deduplication) và hợp nhất dữ liệu từ nhiều nguồn khác nhau (TopCV, ITviec, v.v.) về một cấu trúc chung duy nhất.

## Lưu trữ
- **Định dạng:** `.parquet` (Siêu nén, truy vấn cột cực nhanh)
- **Vị trí:** `s3://jobit-silver/`

## Quá trình biến đổi (bởi dbt)
1. **Làm sạch chuỗi:** Xóa HTML tags thừa trong description.
2. **Parse Mức lương:** Biến đổi "10-15 triệu" thành `salary_min = 10000000`, `salary_max = 15000000`.
3. **Parse Ngày tháng:** Chuẩn hóa `posted_date` và `expired_date` về chuẩn ISO-8601.
4. **Deduplication:** Nếu một Job đăng trên cả TopCV và ITviec, gộp chúng lại làm một bảng ghi duy nhất dựa trên `job_title` và `company_name`.

---

# 4. Gold Layer (Tầng phân tích / Data Warehouse)

## Mục đích
Được thiết kế dưới dạng **Star Schema** (Mô hình sao) hoặc các bảng Data Mart cực rộng (One-Big-Table). Tầng này phục vụ trực tiếp cho các công cụ BI (Power BI) và API hiển thị.

## Lưu trữ
- **Định dạng:** `.parquet`
- **Vị trí:** `s3://jobit-gold/`

## Star Schema Overview
```text
                    dim_date
                        │
                        │
                        ▼

dim_company ─── fact_job_posting ─── dim_location
                        │
                        │
                        ▼

                   dim_source
                        │
                        │
                        ▼

                  dim_job_family
```

---

# 5. Các bảng quan trọng trong Gold Layer

## 5.1. fact_job_posting
Bảng lưu trữ các giá trị đo lường và khóa ngoại trỏ tới các Dimensions.
```sql
-- Cấu trúc logic (dbt model: fct_job_posting.sql)
SELECT
    surrogate_job_key,
    date_key,
    company_key,
    source_key,
    location_key,
    family_key,
    active_job_count,
    salary_min,
    salary_max,
    is_expired
FROM ...
```

## 5.2. dim_company
Mô tả doanh nghiệp. Có thể sử dụng **SCD Type 2** để lưu lịch sử thay đổi (ví dụ công ty thay đổi quy mô từ 100 lên 500 nhân viên).
```sql
-- Cấu trúc logic (dbt model: dim_company.sql)
SELECT
    company_key,
    company_id,
    company_name,
    industry,
    company_size,
    effective_from,
    effective_to,
    is_current
FROM ...
```

## 5.3. Bridge Table (Cho Skills)
Vì một Job có thể yêu cầu nhiều Kỹ năng (Python, SQL, AWS) và một Kỹ năng thuộc về nhiều Job (Many-to-Many), Star Schema chuẩn không xử lý tốt việc này.
Giải pháp là sử dụng bảng cầu nối (Bridge Table):

```text
fact_job_posting  <---(1:N)---> bridge_job_skill <---(N:1)---> dim_skill
```

---

# 6. Pipeline thực thi (với dbt-duckdb)

Thay vì insert từng dòng vào PostgreSQL, pipeline hoạt động theo mô hình ELT trên file:

1. Airflow gọi lệnh `dbt run`.
2. dbt biên dịch file SQL thành các lệnh DuckDB.
3. DuckDB chạy ngầm lệnh:
   ```sql
   -- Ví dụ cách DuckDB đọc trực tiếp S3 và ghi S3
   COPY (
       SELECT title, salary_min, salary_max
       FROM read_json_auto('s3://jobit-bronze/.../*.jsonl')
       WHERE salary_min > 0
   ) TO 's3://jobit-silver/cleaned_jobs.parquet' (FORMAT PARQUET);
   ```
4. Hệ thống hoàn tất mà không cần một server database truyền thống nào.

---

# 7. Phục vụ dữ liệu (Data Serving)

- **Với Power BI:** Có thể dùng ODBC driver của DuckDB để kết nối trực tiếp vào file Parquet trên Floci S3.
- **Với FastAPI:** Import thư viện `duckdb`, chạy query SQL thẳng vào `s3://jobit-gold/fact_job_posting.parquet` và trả kết quả JSON về cho Frontend trong vài mili-giây.
