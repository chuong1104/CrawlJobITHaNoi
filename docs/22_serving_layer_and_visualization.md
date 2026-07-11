# 22. Tầng Phục Vụ Dữ Liệu (Serving Layer) & Visualization

Tài liệu này trình bày chi tiết kiến trúc, công nghệ và các bước triển khai Tầng Phục Vụ (Serving Layer). Đây là chặng cuối cùng trong Data Platform, nơi dữ liệu từ kho (Data Warehouse) được phơi bày ra ngoài để người dùng cuối tương tác qua **Giao diện Web Backend (FastAPI)** và **Hệ thống Dashboard (Power BI)**.

---

## 1. Triết Lý Kiến Trúc Tầng Phục Vụ

Việc phục vụ dữ liệu được thiết kế theo hướng **Decoupled (Tách biệt hoàn toàn)** để tối ưu hiệu năng và tận dụng thế mạnh của từng công cụ:

1. **Analytical Queries (BI):** Power BI sẽ kết nối trực tiếp vào file `dwh.duckdb` cục bộ thông qua ODBC Driver. Cấu trúc lưu trữ dạng cột (Columnar) của DuckDB hỗ trợ truy vấn các mô hình Star Schema (Aggregate millions of rows) trong tích tắc mà không cần một server cơ sở dữ liệu riêng biệt.
2. **Transactional/Search Queries (Web API):** Web backend (FastAPI) sẽ đọc dữ liệu từ **PostgreSQL**. Dữ liệu đã được đồng bộ lên PostgreSQL dưới dạng Materialized View `mart_api.latest_jobs_flat`. Bảng này đã được Denormalize (khử chuẩn hóa, không cần JOIN), đính kèm GIN Index để Full-text search siêu tốc dưới 50ms.

---

## 2. Thiết Kế Giao Diện Web & API (Web Portal)

Ứng dụng Web này đóng vai trò như một "Công cụ Khám phá Dữ liệu Trực quan" (Data Explorer), cho phép người dùng tìm kiếm tin tuyển dụng, xem phân tích nhanh và theo dõi xu hướng.

### 2.1. Tech Stack (Công nghệ sử dụng)
- **Backend Framework:** `FastAPI` (Python) - Tốc độ cực cao nhờ kiến trúc ASGI.
- **Database Driver:** `asyncpg` (Chạy ở chế độ async) kết nối tới PostgreSQL để chịu tải hàng ngàn request/giây.
- **Frontend HTML/JS:** Sử dụng thẻ Semantic HTML5 và Vanilla JavaScript (ES6+), thao tác DOM trực tiếp kết hợp Fetch API.
- **Frontend CSS:** Dùng **Vibrant Dark Mode** (Glassmorphism).

### 2.2. Danh sách API Endpoints (FastAPI)

1. **`GET /api/v1/jobs`**
   - **Mục đích:** Lấy danh sách tin tuyển dụng.
   - **Xử lý:** Backend sẽ truy vấn bảng `mart_api.latest_jobs_flat` trong PostgreSQL. Nếu có keyword, sử dụng toán tử `@@ to_tsquery()` của PostgreSQL để search Full-text.
   
2. **`GET /api/v1/jobs/{job_id}`**
   - **Mục đích:** Lấy chi tiết một tin tuyển dụng cụ thể kèm mô tả công việc (Lấy từ Silver Layer do Tầng Gold không lưu Text dài).
   
3. **`GET /api/v1/stats/summary`**
   - **Mục đích:** Lấy các con số tóm tắt (Tổng tin đang mở, Mức lương trung bình, Tỉ lệ).
   - **Sử dụng:** Lấy số liệu tính toán sẵn từ View `dwh.mv_kpi_realtime` trong PostgreSQL để hiển thị trên Dashboard Web.

---

## 3. Hướng Dẫn Kết Nối Power BI (Dashboard)

Với kiến trúc mới, Power BI kết nối thẳng vào **DuckDB** thông qua ODBC.

### 3.1. Cài đặt ODBC
1. Cài đặt DuckDB ODBC Driver cho Windows.
2. Khai báo chuỗi kết nối: `Driver=DuckDB Driver;Database=D:\JobITVN\job_scraper_de_project\data\dwh.duckdb;` trong tùy chọn ODBC của Power BI.

### 3.2. Mô hình dữ liệu (Star Schema)
Khi tải dữ liệu vào Power BI, sử dụng trực tiếp các bảng/view do `dbt` tạo ra trong DuckDB:
- **Fact:** `fct_job_posting`
- **Dimensions:** `dim_company`, `dim_skill`, `dim_job_attributes`, `dim_location`
- Sử dụng chế độ **Import** (tải vào RAM) hoặc **DirectQuery** nếu muốn dữ liệu thay đổi lập tức sau khi dbt chạy xong.

---

## 4. Kịch Bản Tương Lai: Tích Hợp AI (Machine Learning)

1. **Salary Prediction API:** FastAPI tích hợp Model Predict Salary để tính lương cho các job "Thỏa thuận".
2. **Semantic Search:** Thay thế Full-Text Search PostgreSQL bằng Vector Similarity (Qdrant/Milvus).

**Tóm lại:** Việc chia tách Web API dùng PostgreSQL và Power BI dùng DuckDB mang lại sự cân bằng hoàn hảo giữa khả năng tìm kiếm đồng thời (Concurrency) và phân tích chuyên sâu (Analytics).
