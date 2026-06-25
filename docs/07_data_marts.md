# Data Marts Design

## Overview

Data Mart là tầng dữ liệu phục vụ trực tiếp cho từng nhóm người dùng hoặc từng hệ thống downstream (tầng ngọn). 

Thay vì để các ứng dụng (Dashboard, API, Machine Learning) truy vấn trực tiếp vào Data Warehouse chứa hàng chục bảng Fact và Dimension chằng chịt, chúng ta xây dựng các Data Mart được "trải phẳng" (Flat tables) hoặc "tổng hợp sẵn" (Pre-aggregated). Điều này đảm bảo tốc độ truy xuất tính bằng mili-giây.

Dựa trên mã nguồn hiện tại của dự án (xem `src/schema/gold.py` và `src/gold/gold_exporter.py`), Data Marts được chia làm 3 nhóm chính: **BI Mart**, **ML Mart** và **API Mart**.

---

# 1. BI Marts (Dành cho PowerBI / Reporting)

Được export ra định dạng Parquet thông qua DuckDB để các công cụ BI đọc trực tiếp với tốc độ cao nhất.

## 1.1 `DemandTrendMart` (Xu hướng nhu cầu)
Mục đích: Theo dõi tổng lượng Job tuyển dụng theo từng tháng, phân chia theo ngành nghề.
* **Schema:**
  * `year`: Năm
  * `month`: Tháng
  * `industry`: Ngành nghề
  * `total_jobs`: Tổng số tin tuyển dụng

## 1.2 `SalaryByCompanyMart` (Mức lương theo công ty)
Mục đích: Phân tích mức lương trung bình, tối thiểu và tối đa mà mỗi công ty/ngành nghề sẵn sàng trả.
* **Schema:**
  * `company_name`: Tên công ty
  * `industry`: Ngành nghề
  * `avg_salary`: Lương trung bình
  * `min_salary`: Lương thấp nhất
  * `max_salary`: Lương cao nhất

---

# 2. ML Mart (Dành cho Machine Learning)

Data Scientists không thích viết SQL phức tạp để join bảng. Họ cần một bảng Flat chứa đầy đủ các "Features" (đặc trưng) và "Labels" (nhãn) để huấn luyện mô hình.

## 2.1 `JobFeaturesML` (Đặc trưng công việc)
Mục đích: Dùng để train các mô hình dự đoán mức lương hoặc Recommendation Engine.
* **Schema:**
  * `job_id`: ID định danh
  * `industry`: Ngành nghề
  * `company_size_category`: Quy mô công ty
  * `experience_min_years`: Yêu cầu kinh nghiệm (số)
  * `is_intern`: Có phải Intern không (boolean)
  * `is_fresher`: Có phải Fresher không (boolean)
  * `label_salary`: Mức lương (Target variable để dự đoán)

---

# 3. API Mart (Dành cho Web Portal & Backend)

Phục vụ cho Web App (VueJS/React) tìm kiếm việc làm siêu tốc độ. Bảng này được Materialized trực tiếp trong cơ sở dữ liệu.

## 3.1 `LatestJobsFlatAPI`
Mục đích: Bảng "phẳng" (Flat view) chứa toàn bộ thông tin cần hiển thị cho User trên website, không cần Join bất cứ bảng nào nữa.
* **Schema:**
  * `id`: ID
  * `job_title`: Tiêu đề (đã chuẩn hóa)
  * `company_name`: Tên công ty
  * `industry`: Ngành nghề
  * `source_name`: Nguồn cào
  * `job_level`, `job_type`, `work_mode`: Các thuộc tính công việc
  * `salary_display`, `salary_min_vnd`, `salary_max_vnd`: Thông tin lương
  * `experience_min_years`, `experience_max_years`: Thông tin kinh nghiệm
  * `deadline_date`: Hạn chót
  * `canonical_url`: Link gốc
  * `skills`: Mảng (Array) các kỹ năng (dùng cho GIN Index tìm kiếm cực nhanh)
  * `locations`: Mảng (Array) các địa điểm

---

# 4. Data Mart Refresh Strategy

* Các Data Marts được làm mới (Refresh) **hàng ngày** ngay sau khi tiến trình load Data Warehouse hoàn tất.
* Cơ chế xuất file: Sử dụng `src/gold/gold_exporter.py` để dùng DuckDB đọc dữ liệu từ Postgres DWH và đẩy ra thành các file `.parquet` độc lập.
* **Lợi ích:** Website và Dashboard chạy hoàn toàn tách biệt với Database chính. Kể cả khi hệ thống ETL đang chạy nặng nề, trải nghiệm tìm kiếm của User trên Web không hề bị ảnh hưởng.

---

# 5. Downstream Applications (Đầu Ra Sản Phẩm Hoàn Chỉnh)

Kiến trúc Data Mart hiện tại đã thiết lập nền móng vô cùng vững chắc. Từ các Mart này, JobITVN sẽ được phát triển thành một hệ sinh thái sản phẩm công nghệ (Production-Grade Product) hoàn chỉnh với các mảnh ghép sau:

## 5.1 Hệ Sinh Thái Web App (JobITVN Portal)
Được "nuôi sống" trực tiếp bởi **API Mart** (`LatestJobsFlatAPI`), đây sẽ là sản phẩm mũi nhọn tiếp cận người dùng cuối (Sinh viên/Người tìm việc).

* **Backend (FastAPI / Node.js):** 
  * Cung cấp các RESTful APIs siêu tốc độ.
  * Tích hợp LLM (OpenAI/HuggingFace) để nhúng Vector cho tính năng **Semantic Search** (Tìm kiếm theo ngữ nghĩa). Sinh viên tìm "Làm việc với dữ liệu lớn" sẽ tự động mapping ra "Data Engineer" nhờ Vector Database (pgvector/Qdrant).
  * Tích hợp **Recommendation Engine** (từ bảng `JobFeaturesML` và hành vi người dùng) để tạo ra API cá nhân hóa: "Việc làm dành riêng cho bạn".
* **Frontend (Next.js / Vue 3):**
  * Giao diện UI/UX hiện đại (Dark mode, Glassmorphism).
  * Cung cấp thanh tìm kiếm thông minh, bộ lọc chi tiết (Lương, Location, Remote).
  * Tự động hiển thị các cảnh báo "Việc làm sắp hết hạn" hoặc "Việc làm đang hot".

## 5.2 Real-time Dashboard (Kết nối Power BI)
Lấy dữ liệu từ **BI Marts** (`DemandTrendMart`, `SalaryByCompanyMart`), chúng ta xây dựng hệ thống báo cáo Quản trị và Thị trường.

* **Real-time Streaming:** Chuyển đổi kiến trúc sang dạng Kappa/Lambda với **Apache Kafka** hoặc **Debezium (CDC)**. Khi có một Job mới vừa được đăng trên mạng, tín hiệu sẽ chạy thẳng qua Kafka, biến đổi qua Spark Streaming/Flink và đẩy thẳng lên màn hình Power BI của Admin trong vài giây.
* **IT Market Insights (Sản phẩm thương mại hóa):** Đưa các biểu đồ PowerBI nhúng trực tiếp (Power BI Embedded) lên Web App để người dùng tự tra cứu (Ví dụ: "Báo cáo mức lương Fresher Data Engineer tháng này"). Các báo cáo chuyên sâu có thể được đóng gói bán cho Headhunters và HR.

## 5.3 Hệ Thống Cảnh Báo (Notification & Alerting System)
* **Job Alert System:** Cho phép người dùng đăng ký nhận thông báo qua Email hoặc Telegram. Khi **API Mart** xuất hiện một Job mới khớp với kỹ năng của user, một worker ngầm (Celery/Airflow) sẽ tự động trigger gửi tin nhắn báo cơ hội việc làm ngay lập tức.
