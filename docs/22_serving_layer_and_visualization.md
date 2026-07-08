# 22. Tầng Phục Vụ Dữ Liệu (Serving Layer) & Visualization

Tài liệu này trình bày chi tiết kiến trúc, công nghệ và các bước triển khai Tầng Phục Vụ (Serving Layer). Đây là chặng cuối cùng trong Data Platform, nơi dữ liệu từ kho (Data Warehouse) được phơi bày ra ngoài để người dùng cuối tương tác qua **Giao diện Web Backend (FastAPI)** và **Hệ thống Dashboard (Power BI)**.

---

## 1. Triết Lý Kiến Trúc Tầng Phục Vụ

Sau khi dữ liệu đã được tổng hợp ở Tầng Gold, chúng ta có 3 tệp dữ liệu đích: `mart_api` (trong PostgreSQL), `mart_bi` (Parquet) và `mart_ml` (Parquet). Việc phục vụ dữ liệu sẽ được thiết kế theo hướng **Decoupled (Tách biệt hoàn toàn)** để tối ưu hiệu năng:

1. **Analytical Queries (BI):** Power BI sẽ kết nối trực tiếp để quét các file Parquet hoặc truy vấn DirectQuery xuống DWH PostgreSQL cho mục đích vẽ biểu đồ nặng (Aggregate millions of rows). Tải này hoàn toàn cách ly với web.
2. **Transactional/Search Queries (Web API):** Web backend chỉ đọc duy nhất từ Materialized View `mart_api.latest_jobs_flat`. Bảng này đã được Denormalize (khử chuẩn hóa, không cần JOIN), đính kèm GIN Index để Full-text search siêu tốc dưới 50ms.

---

## 2. Thiết Kế Giao Diện Web & API (Web Portal)

Ứng dụng Web này đóng vai trò như một "Công cụ Khám phá Dữ liệu Trực quan" (Data Explorer), cho phép người dùng tìm kiếm tin tuyển dụng, xem phân tích nhanh và theo dõi xu hướng.

### 2.1. Tech Stack (Công nghệ sử dụng)
- **Backend Framework:** `FastAPI` (Python) - Tốc độ cực cao nhờ kiến trúc ASGI (Asynchronous Server Gateway Interface), hỗ trợ sinh tài liệu Swagger UI tự động.
- **Database Driver:** `asyncpg` hoặc `SQLAlchemy` (Chạy ở chế độ async) để chịu tải hàng ngàn request/giây.
- **Frontend HTML/JS:** Sử dụng thẻ Semantic HTML5 và Vanilla JavaScript (ES6+), thao tác DOM trực tiếp kết hợp Fetch API. Không sử dụng thư viện nặng nề như React/Angular cho một cổng thông tin khám phá dữ liệu siêu tốc.
- **Frontend CSS (Aesthetics):** Sử dụng **Vibrant Dark Mode** (Glassmorphism). Cấu trúc CSS thuần với các biến CSS (CSS Variables) quản lý Theme. Các Card (Thẻ tin tuyển dụng) sẽ có nền mờ (blur), viền neon mỏng, và hiệu ứng hover 3D bắt mắt.

### 2.2. Danh sách API Endpoints (FastAPI)

1. **`GET /api/v1/jobs`**
   - **Mục đích:** Lấy danh sách tin tuyển dụng.
   - **Tham số:** `page`, `limit`, `search_query` (từ khóa), `skill` (lọc theo kỹ năng), `location` (lọc theo địa điểm).
   - **Xử lý:** Backend sẽ truy vấn bảng `mart_api.latest_jobs_flat`. Nếu có `search_query`, sử dụng toán tử `@@ to_tsquery()` của PostgreSQL để search Full-text tốc độ cao.
   
2. **`GET /api/v1/jobs/{job_id}`**
   - **Mục đích:** Lấy chi tiết một tin tuyển dụng cụ thể kèm mô tả công việc (Lấy từ Silver Layer do Tầng Gold không lưu Text dài).
   
3. **`GET /api/v1/stats/summary`**
   - **Mục đích:** Lấy các con số tóm tắt (Tổng tin đang mở, Mức lương trung bình, Top 5 Kỹ năng hot nhất trong ngày).
   - **Sử dụng:** Để render các thẻ KPI (Key Performance Indicators) trên đỉnh Web Dashboard.

### 2.3. Cấu trúc Thư mục Code Dự kiến
```text
src/
└── api/
    ├── main.py              # Entry point của FastAPI
    ├── database.py          # Kết nối PostgreSQL (Connection Pool)
    ├── routers/
    │   └── jobs.py          # Chứa các Endpoints API
    └── static/              # Chứa tài nguyên Web Frontend
        ├── index.html       # Giao diện Web chính
        ├── styles.css       # File CSS Premium Dark Mode
        ├── app.js           # Logic gọi API và Render HTML
        └── assets/          # Hình ảnh, Icons
```

---

## 3. Hướng Dẫn Kết Nối Power BI Real-Time

Mặc dù Data Analyst có thể tải file `.parquet` từ `mart_bi` vào Power BI để vẽ biểu đồ offline nhanh gọn, nhưng nếu muốn một Dashboard mang tính chất Real-time (Thời gian thực), chúng ta thiết lập cơ chế **DirectQuery** với PostgreSQL.

### 3.1. Cài đặt và Kết nối từ Windows vào WSL
1. **Cài đặt Power BI Desktop:** Tải từ Microsoft Store trên Windows (Vì Power BI không hỗ trợ WSL/Linux).
2. **Cài đặt Npgsql (Tùy chọn):** Tải bản `.msi` từ [trang chủ Npgsql](https://github.com/npgsql/npgsql/releases) (chọn bản 4.0.10+ kèm *Npgsql GAC Installation*) nếu Power BI báo thiếu driver PostgreSQL. Các bản Power BI mới thường đã có sẵn.
3. **Kết nối Mạng:** Theo mặc định, Windows có thể truy cập PostgreSQL chạy trên WSL thông qua địa chỉ `localhost:5432`.

### 3.2. Cấu hình DirectQuery
1. Mở Power BI > Chọn **Get Data** > **PostgreSQL database**.
2. Nhập Server: `localhost` và Database: `jobitvn`.
3. **Cực kỳ Quan trọng:** Tại Data Connectivity mode, chọn **DirectQuery** thay vì Import.
   - *Import:* Tải data vào RAM (Không realtime).
   - *DirectQuery:* Bắn lệnh SQL thẳng xuống PostgreSQL mỗi khi click filter (Luôn là dữ liệu mới nhất).
4. Nhập User/Pass (ví dụ: `postgres` / `postgres`). Nếu báo lỗi SSL, bỏ tick "Encrypt connections" hoặc nhấn OK để dùng Unencrypted.
5. Import các bảng từ Schema `dwh` (`fct_job_posting`, `dim_company`, `dim_skill`, v.v.) hoặc các view tính toán sẵn trong `mart_bi`. Kéo thả thiết lập relationship 1-nhiều.

### 3.3. Cấu hình Tự động Refresh (Page Refresh)
Để màn hình tự động chớp và load data mới (ví dụ khi treo trên màn hình Tivi):
1. Click vào khoảng trống trên màn hình Report.
2. Mở tab **Format your report page** (biểu tượng cây cọ sơn).
3. Tìm mục **Page refresh** và bật chế độ **On**.
4. Thiết lập thời gian (ví dụ: **5 seconds**). Power BI sẽ tự động query PostgreSQL mỗi 5 giây.
> **Mẹo:** Nên dùng các View Aggregate đã tính toán sẵn (như `kpi_daily_summary`) để Dashboard chạy siêu tốc thay vì dùng bảng Fact khổng lồ.

### 3.4. Gợi ý Xây dựng Report (Pages)
- **Trang 1: Overview:** Thẻ Card KPI (Total Jobs, Median Salary), Biểu đồ Line xu hướng đăng tin.
- **Trang 2: Skill Analysis:** Biểu đồ Bar Top Kỹ năng yêu cầu, Scatter plot tương quan lương và kỹ năng.
- **Trang 3: Company Insights:** Bảng chi tiết Top các công ty đăng tuyển nhiều nhất phân theo quy mô.

---

## 4. Kịch Bản Tương Lai: Tích Hợp AI (Machine Learning)

Khi giao diện Web và Power BI đã chạy mượt mà, Tầng Phục Vụ sẽ được nâng cấp mở rộng bằng cách tích hợp trực tiếp **AI Models**:
1. **Salary Prediction API:** Một endpoint `/api/v1/predict-salary` được thiết lập trên FastAPI. Khi tin tuyển dụng trên Web ghi "Mức lương: Thỏa thuận", Web App sẽ gọi API này, đẩy Data vào model Machine Learning (được train từ file `mart_ml/job_features.parquet`) để trả ra con số dự đoán (Ví dụ: "AI Dự đoán: 15-20 Triệu VND").
2. **Semantic Search:** Thay đổi ô tìm kiếm trên Web từ việc tìm theo Text Match (toán tử LIKE) sang Vector Similarity (Tìm kiếm theo Ngữ nghĩa). FastAPI sẽ kết nối với một Vector Database (như Qdrant/Milvus) chứa các Vector Embeddings của Job Descriptions.

---

**Tóm lại:** Việc tách riêng tầng API (đọc View siêu nhẹ) và tầng BI (DirectQuery/Parquet) đảm bảo hệ thống có thể scale lên hàng chục ngàn lượt truy cập mà không gặp rủi ro "thắt cổ chai" CSDL. Mọi thứ đã sẵn sàng để lập trình ngay khi bạn yêu cầu.
