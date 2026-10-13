# 25. Hướng Dẫn Deploy Web UI & API Lên Vercel + Neon.tech PostgreSQL (Miễn Phí 100%)

Tài liệu này hướng dẫn chi tiết từng bước để triển khai **Giao diện Web (Frontend)** và **FastAPI Backend** lên đám mây công khai mà **hoàn toàn không tốn chi phí**, **không cần thẻ tín dụng**, và sở hữu đường link HTTPS chuyên nghiệp để đính kèm vào CV / Portfolio.

---

## 1. Kiến Trúc Triển Khai (Decoupled Cloud Architecture)

```
┌───────────────────────────────────────────────┐
│              TRÌNH DUYỆT NGƯỜI DÙNG           │
└───────────────────────▲───────────────────────┘
                        │ HTTPS
┌───────────────────────┴───────────────────────┐
│               VERCEL SERVERLESS               │
│  - Static Hosting: HTML/CSS/JS Dashboard      │
│  - FastAPI Backend (Python Serverless)        │
│  - URL: https://crawl-job-it-hanoi.vercel.app │
└───────────────────────▲───────────────────────┘
                        │ Pooled Connection (TLS/SSL)
┌───────────────────────┴───────────────────────┐
│            NEON.TECH POSTGRESQL CLOUD         │
│  - Free Tier: 500 MB (PostgreSQL 16)          │
│  - Lưu trữ: Schema Silver & DWH Gold (Views)  │
│  - Tích hợp sẵn PgBouncer Connection Pooler   │
└───────────────────────▲───────────────────────┘
                        │ (Đồng bộ khi cào dữ liệu mới)
┌───────────────────────┴───────────────────────┐
│          MÁY LOCAL CỦA BẠN (HOẶC VPS)         │
│  - Scrapers: TopCV, VietnamWorks, ITviec      │
│  - Airflow / DuckDB / dbt Pipeline            │
└───────────────────────────────────────────────┘
```

---

## 2. Hướng Dẫn Từng Bước Chi Tiết

### Bước 1: Tạo Database PostgreSQL Cloud trên Neon.tech (3 phút)

1. Truy cập [https://neon.tech](https://neon.tech) và chọn **Sign Up** (đăng nhập nhanh bằng tài khoản **GitHub**).
2. Sau khi đăng nhập, bấm nút **Create Project**:
   - **Project Name:** `job-it-vn`
   - **Postgres version:** `16` (mặc định)
   - **Region:** Chọn **Singapore (`ap-southeast-1`)** để đạt độ trễ thấp nhất về Việt Nam.
   - Bấm **Create Project**.
3. Lấy chuỗi kết nối Database (**Connection String**):
   - Tại trang **Dashboard** của Project, tìm mục **Connection Details**.
   - Tích chọn ô **Pooled connection** (cực kỳ quan trọng để xử lý các kết nối serverless từ Vercel).
   - Chọn định dạng kết nối: **URL** / **Connection string**.
   - Chuỗi kết nối sẽ có dạng:
     ```text
     postgresql://<username>:<password>@ep-cool-cloud-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
     ```
   - Hãy sao chép và lưu lại chuỗi này vào Notepad.

---

### Bước 2: Nạp Schema và Dữ Liệu lên Neon.tech

Bạn có thể chọn 1 trong 2 cách sau tùy theo trạng thái dữ liệu hiện tại của bạn:

#### Cách A: Di chuyển toàn bộ dữ liệu hiện tại từ Local sang Neon (Khuyên dùng)
Nếu ở máy local bạn đã chạy Docker và đã có sẵn dữ liệu trong PostgreSQL:

1. **Dump dữ liệu từ Docker local ra file SQL:**
   ```bash
   # Mở Terminal (PowerShell/CMD) tại thư mục project
   docker exec -t postgres pg_dump -U airflow -d job_scraper_db --no-owner --no-acl > backup_local.sql
   ```
2. **Restore file backup lên Neon Cloud:**
   *(Lưu ý: Dùng chuỗi kết nối **Direct** - bỏ chữ `-pooler` để chạy lệnh DDL restore)*:
   ```bash
   psql "postgresql://<username>:<password>@ep-cool-cloud.ap-southeast-1.aws.neon.tech/neondb?sslmode=require" -f backup_local.sql
   ```

#### Cách B: Khởi tạo Schema mới từ các file SQL của dự án
Nếu bạn muốn tạo mới cấu trúc bảng trên Neon:
1. Mở công cụ quản lý cơ sở dữ liệu (ví dụ **DBeaver** hoặc **pgAdmin**).
2. Tạo kết nối mới tới Neon bằng chuỗi kết nối đã lấy ở Bước 1.
3. Chạy lần lượt các script trong thư mục `scripts/sql/`:
   - `scripts/sql/silver/01_create_silver_schema.sql`
   - `scripts/sql/silver/02_create_cdc_tables.sql`
   - `scripts/sql/silver/02_create_indexes.sql`
   - `scripts/sql/silver/03_create_procedures.sql`
   - `scripts/sql/silver/04_create_batch_procedures.sql`
   - `scripts/sql/gold/01_create_gold_dwh_schema.sql`
   - `scripts/sql/gold/02_create_materialized_views.sql`
   - `scripts/sql/gold/02_create_gold_procedures.sql`

---

### Bước 3: Đẩy Thay Đổi Mã Nguồn Lên GitHub

Trong dự án đã được chuẩn bị sẵn các file:
- `vercel.json`: Định tuyến request vào Python Serverless.
- `api/index.py`: Điểm kích hoạt ứng dụng FastAPI.
- `api/requirements.txt`: Chứa các dependencies gọn nhẹ dành riêng cho Vercel (không cài các thư viện scraper/Airflow nặng).
- `src/api/main.py`: Đã cấu hình hỗ trợ cả `postgres://` và `postgresql://`.

Chạy các lệnh Git để đẩy toàn bộ code lên GitHub:
```bash
git add vercel.json api/ src/api/main.py docs/
git commit -m "feat: setup vercel deployment configuration and neon cloud db support"
git push origin main
```

---

### Bước 4: Triển Khai Lên Vercel (2 phút)

1. Truy cập [https://vercel.com](https://vercel.com) và đăng nhập bằng tài khoản **GitHub**.
2. Tại trang tổng quan (Dashboard), bấm **Add New...** ➔ Chọn **Project**.
3. Chọn repository `CrawlJobITHaNoi` (hoặc tên repo của bạn) và bấm **Import**.
4. Cấu hình triển khai:
   - **Project Name:** Để mặc định hoặc đặt tên tùy ý (ví dụ: `job-it-vietnam`).
   - **Framework Preset:** Giữ nguyên `Other`.
   - **Root Directory:** Để trống (`./`).
   - Mở rộng mục **Environment Variables** và thêm biến môi trường:
     - **Key:** `DATABASE_URL`
     - **Value:** Dán chuỗi **Pooled connection** của Neon đã lấy ở Bước 1:
       ```text
       postgresql://<username>:<password>@ep-cool-cloud-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
       ```
     - Bấm nút **Add**.
5. Bấm **Deploy**.
6. Chờ khoảng 1-2 phút. Vercel sẽ tự động:
   - Cài đặt các gói từ `api/requirements.txt`.
   - Đóng gói Serverless Function.
   - Cung cấp tên miền công khai dạng: `https://job-it-vietnam.vercel.app`.

---

### Bước 5: Kiểm Tra Kết Quả

1. **Kiểm tra Giao diện Web Dashboard:**
   - Mở đường link Vercel: `https://job-it-vietnam.vercel.app`
   - Kiểm tra các biểu đồ: Phân bổ lương theo kỹ năng, Top công ty tuyển dụng, Phân loại theo kinh nghiệm.
   - Sử dụng thanh tìm kiếm và bộ lọc việc làm.
2. **Kiểm tra API Documentation (Swagger UI):**
   - Truy cập `https://job-it-vietnam.vercel.app/docs` để kiểm tra các API endpoints tương tác trực tiếp.

---

### Bước 6: Quy Trình Vận Hành Cập Nhật Dữ Liệu

Khi bạn muốn cào thêm dữ liệu mới và cập nhật lên web:
1. Mở file `.env` trên máy local của bạn.
2. Đổi giá trị `DATABASE_URL` trỏ trực tiếp tới Neon Cloud:
   ```env
   DATABASE_URL=postgresql://<username>:<password>@ep-cool-cloud.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
3. Chạy pipeline cào và xử lý dữ liệu ở local như bình thường:
   - Scraper tải dữ liệu và nạp vào Silver layer trên Neon.
   - dbt / SQL procedures làm mới Materialized Views trên Neon.
4. Ngay lập tức, trang web trên Vercel sẽ tự động phản ánh dữ liệu mới nhất mà bạn không cần phải redeploy lại web!
