# Data Marts Design (v2.2)

## Overview

Data Mart là tầng dữ liệu phục vụ trực tiếp cho từng nhóm người dùng hoặc từng hệ thống downstream (tầng ngọn). 

Thay vì để các ứng dụng (Dashboard, API, Machine Learning) truy vấn trực tiếp vào Data Warehouse chứa nhiều bảng Fact và Dimension liên kết phức tạp, chúng ta xây dựng các Data Mart được "trải phẳng" (Flat tables) hoặc "tổng hợp sẵn" (Pre-aggregated). Điều này đảm bảo tốc độ truy xuất tính bằng mili-giây và cô lập tải phân tích.

Dự án sử dụng mô hình **Hybrid serving**:
- **BI & ML Marts (Delta Lake S3 & DuckDB):** Dữ liệu được dbt xây dựng trong DuckDB, đồng thời xuất ra **Delta Tables** trên S3 (Floci) để có ACID và Time Travel.
- **API & Power BI Serving (PostgreSQL):** Sử dụng các **Materialized Views** trong PostgreSQL được tối ưu hóa chỉ mục để phục vụ trực tiếp cho các APIs và dashboard với hiệu năng tối đa.

---

# 1. BI Marts (Dành cho Power BI / Reporting - dbt models)

Các mô hình được lưu trữ trong `dbt_jobitvn/models/marts/mart_bi/` để tổng hợp số liệu phân tích:

1. **`agg_company_hiring` (Phân tích tuyển dụng theo công ty):**
   * Tổng số tin tuyển dụng đang mở và mức lương trung bình của từng công ty, phân loại quy mô doanh nghiệp.
2. **`agg_demand_trend` (Xu hướng nhu cầu tuyển dụng):**
   * Theo dõi tổng lượng Job tuyển dụng theo từng tháng, phân chia theo ngành nghề.
3. **`agg_job_lifecycle` (Vòng đời tin tuyển dụng):**
   * Phân tích thời gian trung bình một job duy trì trạng thái hoạt động trước khi CLOSED/EXPIRED, và tỷ lệ chuyển đổi trạng thái của các tin.
4. **`agg_jobs_by_city` (Việc làm theo địa phương):**
   * Thống kê số lượng việc làm, lương trung bình và tỷ lệ fresher của từng tỉnh thành.
5. **`agg_remote_ratio_by_role` (Tỷ lệ làm việc từ xa):**
   * Thống kê tỷ lệ tin tuyển dụng cho phép làm Onsite, Hybrid hoặc Remote theo từng vị trí (Job Family).
6. **`agg_salary_by_experience` (Lương theo kinh nghiệm):**
   * Phân tích tương quan mức lương trung bình với số năm kinh nghiệm yêu cầu.
7. **`agg_salary_by_skill` (Lương theo kỹ năng):**
   * Thống kê mức lương trung bình, tối thiểu, tối đa ứng với từng kỹ năng cụ thể.
8. **`agg_skill_trend_weekly` (Xu hướng kỹ năng hàng tuần):**
   * Đo lường mức độ tăng trưởng (growth rate), xếp hạng và label xu hướng (`RISING_FAST`, `STABLE`, etc.) của các kỹ năng IT qua từng tuần.
9. **`agg_top_skills_by_role` (Kỹ năng theo vai trò):**
   * Top các kỹ năng được yêu cầu nhiều nhất cho từng vai trò công việc (Data Engineer, Backend, Frontend, etc.).
10. **`kpi_daily_summary` (Tổng hợp KPI vận hành hàng ngày):**
    * Lưu trữ các chỉ số hoạt động tổng quát của thị trường tuyển dụng theo từng ngày chạy.

---

# 2. ML Mart (Dành cho Machine Learning)

Data Scientists cần các bảng Flat chứa đầy đủ các "Features" (đặc trưng) và "Labels" (nhãn) để huấn luyện mô hình dự đoán.

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

# 3. API Marts (Dành cho Web Portal & Backend - PostgreSQL Materialized Views)

Phục vụ cho Web App tìm kiếm việc làm siêu tốc độ. Các view này được tối ưu hóa bằng **Materialized Views** trực tiếp trong PostgreSQL DWH để API phản hồi dưới 100ms.

## 3.1 `dwh.mv_active_jobs_summary`
Mục đích: Bảng "phẳng" (Flat view) chứa thông tin cần hiển thị cho User trên website và tìm kiếm nhanh, không cần JOIN phức tạp.
* **Schema:**
  * `job_id`, `company_id`, `source_id`: Các khóa định danh thực thể.
  * `canonical_url`: Link gốc tin tuyển dụng.
  * `job_status`: Trạng thái tin tuyển dụng hiện tại.
  * `snapshot_id`: ID của snapshot hiện hành.
  * `title_clean`: Tiêu đề công việc sạch quảng cáo.
  * `salary_min`, `salary_max`, `salary_avg`, `salary_currency`: Chi tiết lương.
  * `experience_min_years`, `experience_max_years`: Yêu cầu kinh nghiệm.
  * `job_level`, `job_type`, `work_mode`, `job_family`: Phân loại công việc.
  * `deadline_date_key`: Ngày hết hạn (định dạng khóa).
  * `is_intern`, `is_fresher`: Cờ phân loại nhanh.
  * `first_seen_date_key`, `last_seen_date_key`: Theo dõi thời điểm xuất hiện.
  * `company_name`, `company_industry`: Thông tin công ty đã phi chuẩn hóa.

## 3.2 `dwh.mv_kpi_realtime`
Mục đích: Trả về nhanh các chỉ số KPI thị trường cho API/Dashboard (Tổng việc làm, số công ty tuyển, mức lương TB, tỷ lệ fresher, tỷ lệ remote), đồng bộ với dbt Semantic Layer.

## 3.3 `dwh.mv_salary_by_skill`
Mục đích: Cache kết quả truy vấn phân tích lương trung bình, median, min, max và xếp hạng nhu cầu/mức lương cho từng kỹ năng.

## 3.4 `dwh.mv_jobs_by_location`
Mục đích: Cache số liệu phân bổ job, lương trung bình và tỷ lệ việc làm cho từng tỉnh thành (Hà Nội, TP.HCM, Đà Nẵng) phục vụ trực quan hóa bản đồ trên Power BI.

---

# 4. Data Mart Refresh & Maintenance Strategy

* **PostgreSQL Refresh:** Sau khi load DWH, Airflow gọi stored procedure `dwh.sp_refresh_all_materialized_views()` để refresh concurrently tất cả materialized views. Việc này không gây lock bảng đọc, API vẫn hoạt động bình thường.
* **S3 Delta Export:** `GoldExporter` sử dụng DuckDB đọc từ Postgres DWH và ghi đè vào các Delta tables trên S3 (`s3://jobit-gold/gold/mart_bi/`).
* **Delta Vacuum:** Cuối pipeline, task `vacuum_delta_tables` chạy lệnh `VACUUM` trên các Delta tables để dọn dẹp log lịch sử và các tệp tin Parquet cũ quá 7 ngày, giải phóng bộ nhớ S3.
