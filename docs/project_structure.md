# Cấu Trúc Thư Mục Dự Án Job Scraper DE

Tài liệu này giải thích chi tiết chức năng của từng thư mục, mục đích sử dụng và nhiệm vụ của các thư mục con bên trong dự án.

## Tổng Quan Cấu Trúc

```text
job_scraper_de_project/
├── dags/
├── data/
├── dbt_jobitvn/
├── docs/
├── logs/
├── plugins/
├── scripts/
├── src/
├── tests/
└── venv/
```

---

## Chi Tiết Từng Thư Mục

### 1. `dags/`
- **Mục đích:** Chứa các DAG (Directed Acyclic Graph) của Apache Airflow.
- **Cách dùng:** Airflow sẽ quét thư mục này để tìm các file định nghĩa luồng công việc (workflow). Bạn tạo hoặc chỉnh sửa các file Python ở đây để lên lịch tự động cho các tác vụ như cào dữ liệu, xử lý dữ liệu và chạy dbt.
- **File tiêu biểu:** `daily_pipeline.py` (Định nghĩa pipeline chạy hàng ngày).

### 2. `data/`
- **Mục đích:** Đóng vai trò là bộ nhớ đệm tạm thời (local buffer/staging) trên máy hoặc môi trường phát triển cục bộ, trước khi dữ liệu được đẩy lên S3 (Floci). Dù mục tiêu chính là lưu trữ trên S3, thư mục này vẫn tồn tại vì:
  1. **An toàn dữ liệu (Buffer):** Khi cào dữ liệu, ghi file xuống ổ cứng cục bộ (vào `data/bronze/`) sẽ an toàn hơn. Nếu mạng chập chờn hoặc kết nối tới S3/Floci bị lỗi, dữ liệu đã cào không bị mất. Sau đó, một tác vụ đồng bộ (sync) sẽ đẩy các file này lên S3.
  2. **Test/Phát triển (Local Dev):** Giúp lập trình viên có thể chạy thử pipeline ở máy cá nhân (Local) mà không cần phải kết nối hoặc làm rác hệ thống lưu trữ S3 thực tế.
- **Cách dùng:** Nơi lưu trữ file tạm thời trong quá trình cào, hoặc đọc/ghi khi phát triển local. Cấu trúc bên trong mô phỏng đúng như trên S3 theo kiến trúc Medallion:
  - `bronze/`: Lưu trữ dữ liệu thô (raw data) vừa mới cào từ các trang web về, chuẩn bị đẩy lên Bucket S3 ở layer Bronze.
  - `silver/`: (Local cache) Chứa dữ liệu đã được làm sạch, trước hoặc sau khi tải từ S3.
  - `gold/`: (Local cache) Chứa dữ liệu đã tổng hợp.

### 3. `dbt_jobitvn/`
- **Mục đích:** Thư mục dự án của dbt (Data Build Tool), quản lý quá trình chuyển đổi dữ liệu (Transformation) từ lớp Silver lên Gold bằng SQL.
- **Cách dùng:** Sử dụng các lệnh dbt (như `dbt run`, `dbt test`) bên trong thư mục này để thực thi các model biến đổi dữ liệu trên Data Warehouse.
- **Các thư mục con:**
  - `models/`: Chứa các file `.sql` định nghĩa logic biến đổi dữ liệu (tables, views).
  - `macros/`: Chứa các đoạn mã SQL có thể tái sử dụng (giống như các hàm trong lập trình).
  - `seeds/`: Chứa các file dữ liệu tĩnh (như `.csv`) dùng để load trực tiếp thành bảng lookup/mapping trong database.
  - `tests/`: Định nghĩa các bài kiểm tra chất lượng dữ liệu (Data Quality Tests) trên các model.

### 4. `src/` (Source)
- **Mục đích:** Chứa toàn bộ mã nguồn chính (core logic) của dự án bằng Python.
- **Cách dùng:** Các script và DAG sẽ import (gọi) các hàm và class từ thư mục này để thực thi nhiệm vụ.
- **Các thư mục con:**
  - `extract/`: Chứa logic dùng để cào dữ liệu (scraping), ví dụ như code tương tác với API hoặc HTML của các trang web việc làm.
  - `schema/`: Định nghĩa cấu trúc dữ liệu (Data Schemas), thường dùng Pydantic để kiểm tra tính hợp lệ của dữ liệu đầu vào/đầu ra.
  - `storage/`: Chứa mã nguồn quản lý việc kết nối với cơ sở dữ liệu và lưu trữ (đọc/ghi file, insert database).
  - `sync/`: Chứa các logic đồng bộ hóa hoặc di chuyển dữ liệu giữa các môi trường lưu trữ (ví dụ từ file Bronze vào staging area của cơ sở dữ liệu).

### 5. `scripts/`
- **Mục đích:** Chứa các tập lệnh thực thi độc lập (standalone scripts) thường dùng để test nhanh, chạy thủ công hoặc xử lý một tác vụ cụ thể ngoài pipeline.
- **Cách dùng:** Chạy trực tiếp qua terminal (ví dụ: `python scripts/run_scrapers.py`).
- **File tiêu biểu:**
  - `run_scrapers.py`: Kích hoạt quá trình cào dữ liệu theo cách thủ công.
  - `login_linkedin_interactive.py`: Hỗ trợ đăng nhập thủ công/lấy cookies đối với những trang yêu cầu xác thực phức tạp.

### 6. `tests/`
- **Mục đích:** Chứa các bài kiểm tra tự động (Unit Tests / Integration Tests) cho mã nguồn Python.
- **Cách dùng:** Chạy framework pytest (ví dụ: `pytest tests/`) để đảm bảo các module cào dữ liệu và xử lý hoạt động chính xác sau khi có thay đổi code.
- **File tiêu biểu:** Chứa các test cho các module cụ thể như `test_itviec_full.py`, `test_linkedin_full.py`.

### 7. `logs/`
- **Mục đích:** Lưu trữ các file nhật ký hoạt động (log files) của hệ thống.
- **Cách dùng:** Dùng để kiểm tra, debug và giám sát khi pipeline chạy lỗi. Thư mục này thường chứa log của các scraper hoặc của Airflow.

### 8. `docs/`
- **Mục đích:** Chứa các tài liệu thiết kế, hướng dẫn sử dụng, hoặc kiến trúc của dự án.
- **Cách dùng:** Nơi team phát triển lưu lại các kiến thức và thiết kế hệ thống.

### 9. `plugins/`
- **Mục đích:** Thư mục dành riêng cho các plugin tùy chỉnh của Apache Airflow.
- **Cách dùng:** Nếu bạn viết thêm các Operators, Hooks hoặc Macros mới cho Airflow, bạn sẽ đặt chúng ở đây để Airflow tự động nhận diện.

### 10. `venv/`
- **Mục đích:** Chứa môi trường ảo của Python (Virtual Environment).
- **Cách dùng:** Cô lập các thư viện cài đặt cho dự án này (như pandas, dbt, airflow, selenium...) để không xung đột với hệ thống. Kích hoạt môi trường này trước khi chạy code (`source venv/bin/activate`).
