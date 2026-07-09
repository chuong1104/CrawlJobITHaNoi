# Data Marts Design (v2.1)

## Overview

Data Mart là tầng dữ liệu phục vụ trực tiếp cho từng nhóm người dùng hoặc từng hệ thống downstream (tầng ngọn). 

Thay vì để các ứng dụng (Dashboard, API, Machine Learning) truy vấn trực tiếp vào Data Warehouse chứa hàng chục bảng Fact và Dimension chằng chịt, chúng ta xây dựng các Data Mart được "trải phẳng" (Flat tables) hoặc "tổng hợp sẵn" (Pre-aggregated). Điều này đảm bảo tốc độ truy xuất tính bằng mili-giây và cô lập tải phân tích.

Dự án sử dụng mô hình **Hybrid serving**:
- **BI & ML Marts:** Lưu trữ dưới dạng **Delta Tables** trên S3 (Floci) để có ACID và Time Travel, đồng thời xuất local Parquet làm fallback.
- **API Marts:** Sử dụng **Materialized Views** trong PostgreSQL để phục vụ APIs trực tiếp với hiệu năng tối đa.

---

# 1. BI Marts (Dành cho Power BI / Reporting)

Được xuất ra dưới định dạng Delta Lake trên S3 và Parquet local để Power BI đọc DirectQuery hoặc import nhanh.

## 1.1 `agg_demand_trend` (Xu hướng nhu cầu tuyển dụng)
Mục đích: Theo dõi tổng lượng Job tuyển dụng theo từng tháng, phân chia theo ngành nghề.
* **Schema:**
  * `year`: Năm
  * `month`: Tháng
  * `industry`: Ngành nghề
  * `total_jobs`: Tổng số tin tuyển dụng đang hoạt động

## 1.2 `agg_salary_by_company` (Mức lương theo công ty)
Mục đích: Phân tích mức lương trung bình, tối thiểu và tối đa mà mỗi công ty/ngành nghề sẵn sàng trả.
* **Schema:**
  * `company_name`: Tên công ty
  * `industry`: Ngành nghề
  * `avg_salary`: Lương trung bình
  * `min_salary`: Lương thấp nhất
  * `max_salary`: Lương cao nhất

## 1.3 `agg_skill_trend_weekly` [NEW] (Xu hướng kỹ năng hàng tuần)
Mục đích: Đo lường mức độ tăng trưởng (growth rate) và xu hướng (trend_label, momentum) của các kỹ năng IT.
* **Schema:**
  * `skill_code`, `skill_name`, `skill_category`: Mã, tên và phân loại kỹ năng
  * `week_start_date`: Ngày bắt đầu tuần (Monday)
  * `job_count`: Số lượng job yêu cầu kỹ năng trong tuần
  * `growth_rate_pct`: Tốc độ tăng trưởng so với tuần trước (%)
  * `rolling_4w_avg`: Trung bình trượt 4 tuần để làm mịn dữ liệu
  * `weekly_rank`: Xếp hạng mức độ phổ biến trong tuần
  * `trend_label`: Phân loại xu hướng (`RISING_FAST`, `RISING`, `STABLE`, `DECLINING`)
  * `momentum`: Động lượng xu hướng (`UPWARD`, `SIDEWAYS`, `DOWNWARD`)

---

# 2. ML Mart (Dành cho Machine Learning)

Data Scientists cần một bảng Flat chứa đầy đủ các "Features" (đặc trưng) và "Labels" (nhãn) để huấn luyện mô hình dự đoán.

## 2.1 `job_features` (Đặc trưng công việc)
Mục đích: Train các mô hình dự đoán mức lương hoặc Recommendation Engine. Lưu dưới dạng Delta Table trên S3.
* **Schema:**
  * `job_id`: ID định danh của job posting fact
  * `industry`: Ngành nghề
  * `company_size_category`: Quy mô công ty
  * `experience_min_years`: Yêu cầu kinh nghiệm (năm)
  * `is_intern`: Có phải Intern không (boolean)
  * `is_fresher`: Có phải Fresher không (boolean)
  * `label_salary`: Mức lương trung bình (nhãn để dự đoán)

---

# 3. API Mart (Dành cho Web Portal & Backend - PostgreSQL)

Phục vụ cho Web App (VueJS/React) tìm kiếm việc làm siêu tốc độ. Bảng này được tối ưu bằng **Materialized Views** trực tiếp trong PostgreSQL DWH để API gọi phản hồi < 100ms.

## 3.1 `dwh.mv_active_jobs_summary`
Mục đích: Bảng "phẳng" (Flat view) chứa toàn bộ thông tin cần hiển thị cho User trên website, không cần Join bất cứ bảng nào nữa.
* **Schema:**
  * `job_id`: ID tin tuyển dụng
  * `title_clean`: Tiêu đề đã chuẩn hóa
  * `company_name`: Tên hiển thị của công ty
  * `company_industry`: Ngành nghề doanh nghiệp
  * `salary_avg`, `salary_min`, `salary_max`, `salary_currency`: Thông tin lương
  * `experience_min_years`, `experience_max_years`: Yêu cầu kinh nghiệm
  * `job_level`, `job_type`, `work_mode`: Các thuộc tính phân loại
  * `deadline_date_key`: Khóa ngày hết hạn
  * `canonical_url`: Link gốc tin tuyển dụng
  * `is_intern`, `is_fresher`: Cờ phân loại nhanh

## 3.2 `dwh.mv_kpi_realtime`
Mục đích: Trả về nhanh 12 chỉ số KPI thị trường cho API/Dashboard, đồng bộ với dbt Semantic Layer.

---

# 4. Data Mart Refresh & Maintenance Strategy

* **PostgreSQL Refresh:** Sau khi load DWH, Airflow gọi stored procedure `dwh.sp_refresh_all_materialized_views()` để refresh đồng thời tất cả materialized views ở chế độ **CONCURRENTLY** (không lock bảng đọc, API vẫn hoạt động bình thường).
* **S3 Delta Export:** `GoldExporter` sử dụng DuckDB đọc từ Postgres DWH và ghi đè vào các Delta tables trên S3 (`s3://jobit-gold/gold/mart_bi/`).
* **Delta Vacuum:** Cuối pipeline, task `vacuum_delta_tables` chạy lệnh `VACUUM` trên các Delta tables để dọn dẹp log lịch sử và các tệp tin Parquet cũ quá 7 ngày, giải phóng bộ nhớ S3.
* **Lợi ích:** Hệ thống serving hoàn toàn tách biệt khỏi database transaction nghiệp vụ. Thời gian phản hồi API ổn định ở mức cực thấp, Power BI dashboard load nhanh mà không làm chậm hệ thống crawler/sync.
