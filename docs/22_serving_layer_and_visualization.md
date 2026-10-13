# 22. Tầng Phục Vụ Dữ Liệu (Serving Layer) & Visualization

Tài liệu này trình bày chi tiết kiến trúc, công nghệ và các bước triển khai Tầng Phục Vụ (Serving Layer). Đây là chặng cuối cùng trong Data Platform, nơi dữ liệu từ kho (Data Warehouse) được phơi bày ra ngoài để người dùng cuối tương tác qua **Giao diện Web Backend (FastAPI)** và **Hệ thống Dashboard (Power BI)**.

---

## 1. Triết Lý Kiến Trúc Tầng Phục Vụ

Hệ thống phục vụ dữ liệu được thiết kế theo hướng **Decoupled (Tách biệt hoàn toàn)** để tối ưu hóa hiệu năng, giảm tải cho database và tận dụng thế mạnh của từng công cụ:

1. **Analytical Queries (BI Reporting):** Power BI kết nối vào **PostgreSQL 17 Gold DWH** (hoặc file `jobitvn.duckdb` qua ODBC). Cấu trúc Star Schema với Fact table và Dimension tables cho phép tổng hợp số liệu phân tích nhiều chiều trong thời gian ngắn.
2. **Transactional & Search Queries (Web Portal):** Web backend (FastAPI) đọc dữ liệu từ **PostgreSQL 17** (Materialized Views và Silver/Gold layer).
   - Truy vấn được tăng tốc bằng **GIN Trigram Index (`pg_trgm`)** cho Full-Text Search tiếng Việt không dấu/có dấu trong < 50ms mà không cần duy trì Elasticsearch cluster tốn kém.
   - **SQLAlchemy QueuePool** tái sử dụng kết nối (5 kết nối thường trực, 10 overflow) tránh overhead mở socket liên tục.
   - **In-Memory TTL Cache (`@ttl_cache`)** lưu kết quả các endpoint thống kê nặng (1 tiếng cho skill/company stats, 60 giây cho KPI/job listing), giải phóng tải cho database.

---

## 2. Thiết Kế Giao Diện Web & API (Web Portal)

Ứng dụng Web đóng vai trò như một "Công cụ Khám phá Dữ liệu Tuyển dụng IT Trực quan" (IT Job Data Explorer), cho phép ứng viên và nhà tuyển dụng tra cứu tin việc làm, xem phân tích xu hướng kỹ năng, mức lương và địa điểm theo thời gian thực.

### 2.1. Tech Stack (Công nghệ sử dụng)

- **Backend Framework:** `FastAPI` (Python 3.11+) — Kiến trúc bất đồng bộ ASGI siêu tốc.
- **Connection Management:** `SQLAlchemy 2.0` với `QueuePool` (pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=3600).
- **Caching:** In-Memory TTL Cache (dict + timestamp monotonic, thread-safe, không phụ thuộc Redis) kèm cơ chế dọn dẹp bộ nhớ chủ động.
- **Frontend Architecture:** 
  - **HTML5:** Semantic markup, responsive layout.
  - **CSS3:** Vibrant Dark Mode, hiệu ứng Glassmorphism hiện đại, CSS custom properties.
  - **JavaScript:** Vanilla JS ES6+ (Fetch API, debounce search, DOM rendering), thư viện Chart.js cho biểu đồ trực quan.
  - **Static Serving:** Mount trực tiếp tại root `/` qua `StaticFiles(directory="src/api/static", html=True)`.
- **Serverless Ready:** Sẵn sàng triển khai cloud miễn phí lên **Vercel** thông qua `vercel.json` và entrypoint `api/index.py`.

---

### 2.2. Danh Sách API Endpoints (FastAPI)

Tất cả endpoint đều được tài liệu hóa tự động qua Swagger UI tại `/docs` và ReDoc tại `/redoc`.

| Method | Endpoint | Tags | TTL Cache | Mô tả & Nguồn dữ liệu |
|---|---|---|---|---|
| `GET` | `/health` | System | Không | Healthcheck API, ping DB và kiểm tra chỉ số Connection Pool |
| `GET` | `/jobs` | Jobs | 60 giây | Danh sách tin tuyển dụng có phân trang (`page`, `limit`), lọc nguồn (`source`), tìm kiếm (`search`), địa điểm (`location`), dải lương (`salary`), kinh nghiệm (`experience`), trạng thái hạn nộp (`status`), và sắp xếp (`sort`) |
| `GET` | `/jobs/{job_id}` | Jobs | Không | Xem chi tiết tin tuyển dụng bao gồm JD đầy đủ, địa điểm chuẩn hóa, hạn nộp và link gốc |
| `GET` | `/stats/kpi` | Statistics | 60 giây | KPI thị trường: tổng job active, việc mới 7 ngày, lương TB/median, tỉ lệ công khai lương, việc fresher/remote, top 10 skills (Đọc từ `dwh.mv_kpi_realtime` kèm fallback) |
| `GET` | `/stats/skills` | Statistics | 3600 giây | Top N kỹ năng IT có nhu cầu tuyển dụng cao nhất (Đọc từ `dwh.mv_salary_by_skill`) |
| `GET` | `/stats/companies` | Statistics | 3600 giây | Top N công ty tuyển dụng tích cực nhất (Đọc từ `dwh.mv_active_jobs_summary`) |
| `GET` | `/stats/locations` | Statistics | 3600 giây | Phân bổ số lượng việc làm theo tỉnh/thành phố (Đọc từ `dwh.mv_jobs_by_location`) |
| `GET` | `/stats/salary-by-skill` | Statistics | 3600 giây | Mức lương trung bình và lương tối đa theo từng kỹ năng IT (Đọc từ `dwh.mv_salary_by_skill`) |
| `POST` | `/cache/invalidate` | System | Không | Endpoint kích hoạt xóa sạch cache, được Airflow DAG gọi sau khi hoàn thành pipeline hàng ngày |

---

## 3. Chi Tiết Triển Khai Tính Năng Quan Trọng

### 3.1. Connection Pooling Chống Thắt Cổ Chai

```python
# src/api/main.py
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,           # Số kết nối thường trực
    max_overflow=10,       # Kết nối phụ trợ khi có traffic đột biến
    pool_timeout=30,       # Timeout chờ giải phóng connection
    pool_recycle=3600,     # Tự động refresh connection sau 1 giờ
    pool_pre_ping=True,    # Kiểm tra tính sống còn trước khi thực thi
)
```

### 3.2. TTL Cache Thông Minh Không Cần Redis

```python
# src/api/main.py
def ttl_cache(seconds: int = 300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            now = time.monotonic()
            if cache_key in _cache:
                result, cached_at = _cache[cache_key]
                if now - cached_at < seconds:
                    return result
            result = func(*args, **kwargs)
            _cache[cache_key] = (result, now)
            return result
        return wrapper
    return decorator
```

### 3.3. Tích Hợp Airflow Làm Mới Dữ Liệu Tự Động

Khi pipeline Airflow `daily_job_pipeline` hoàn tất việc nạp dữ liệu vào Silver và refresh Materialized Views ở Gold layer, task cuối cùng sẽ gửi một HTTP POST request đến `/cache/invalidate`. Ngay lập tức, toàn bộ cache thống kê được xóa sạch, đảm bảo người dùng truy cập web luôn nhìn thấy dữ liệu mới nhất mà không cần khởi động lại container API.

---

## 4. Hướng Dẫn Kết Nối Power BI (Dashboard)

Hệ thống hỗ trợ kết nối Power BI trực tiếp qua PostgreSQL ODBC Driver hoặc DuckDB ODBC Driver:

### 4.1. Chuẩn Bị Kết Nối

1. **PostgreSQL Driver:** Cài đặt PostgreSQL ODBC Driver (psqlODBC 64-bit) trên máy chạy Power BI Desktop.
2. **Khai Báo DSN hoặc Chuỗi Kết Nối:**
   - Server: `localhost` (hoặc IP máy chủ/cloud VPS)
   - Port: `5432`
   - Database: `job_scraper_db`
   - User / Password: cấu hình theo `.env`

### 4.2. Khai Thác Mô Hình Dữ Liệu Star Schema

Khi tạo báo cáo trong Power BI, kết nối trực tiếp vào schema `dwh`:
- **Fact Table:** `fct_job_postings`, `fct_job_skills`
- **Dimension Tables:** `dim_date`, `dim_company`, `dim_skill`, `dim_location`
- **Materialized Views:** `mv_kpi_realtime`, `mv_salary_by_skill`, `mv_jobs_by_location`
- **Chế độ kết nối:**
  - **Import Mode:** Tải dữ liệu vào Power BI Desktop để tối ưu hóa tốc độ slicer và DAX measures.
  - **DirectQuery:** Phản ánh dữ liệu theo thời gian thực ngay sau khi Airflow chạy xong.

---

## 5. Kịch Bản Mở Rộng Trong Tương Lai

1. **AI Salary Estimator:** Tích hợp mô hình hồi quy (Gradient Boosting / Random Forest) dự đoán dải lương cho các tin tuyển dụng "Thỏa thuận" dựa trên Title, Location, Skills và Experience.
2. **Vector Semantic Search:** Khi mở rộng hạ tầng máy chủ (>8GB RAM), bổ sung mô hình Vietnamese SBERT kết hợp Qdrant / pgvector để tìm kiếm công việc theo độ tương đồng ngữ nghĩa của CV ứng viên.
