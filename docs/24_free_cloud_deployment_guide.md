# 24. Hướng Dẫn Triển Khai Hệ Thống Data Pipeline Miễn Phí Lên Cloud

Để chạy thử nghiệm toàn bộ hệ thống này (gồm Apache Airflow, PostgreSQL, Floci S3, và FastAPI) trên đám mây (Cloud) hoàn toàn miễn phí, chúng ta cần giải quyết một bài toán lớn về phần cứng:
> **Lưu ý quan trọng về RAM:**
> Apache Airflow là một hệ thống rất nặng, yêu cầu tối thiểu **3GB - 4GB RAM** để vận hành ổn định. Các dịch vụ Cloud miễn phí thông thường (như AWS EC2 t2.micro, Render Free, Fly.io Free, Google Cloud e2-micro) chỉ cung cấp từ **512MB đến 1GB RAM**. Nếu chạy trên các dịch vụ này, hệ thống sẽ bị đứng hoặc báo lỗi tràn bộ nhớ (Out Of Memory - OOM) ngay lập tức khi khởi động Docker.

Giải pháp tối ưu và duy nhất để chạy toàn bộ hệ thống này miễn phí vĩnh viễn là sử dụng **Oracle Cloud Infrastructure (OCI) Always Free Tier**.

---

## 1. Tại Sao Chọn Oracle Cloud Always Free?

Gói miễn phí trọn đời (Always Free) của Oracle Cloud cung cấp cấu hình cực kỳ mạnh mẽ:
* **Vi xử lý:** ARM Ampere A1 (lên đến 4 OCPUs).
* **Bộ nhớ (RAM):** Lên đến **24 GB RAM** (bạn có thể cấp phát toàn bộ 24GB cho 1 máy ảo).
* **Ổ cứng:** 200 GB lưu trữ khối (Block Volume).
* **Băng thông:** 10 TB chuyển dữ liệu ra ngoài mỗi tháng.

Cấu hình này dư sức để bạn chạy mượt mà toàn bộ hệ thống Data Pipeline cùng lúc.

---

## 2. Hướng Dẫn Các Bước Triển Khai Chi Tiết

### Bước 1: Đăng ký tài khoản Oracle Cloud
1. Truy cập trang đăng ký: [https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/)
2. Nhập thông tin cá nhân và thực hiện xác minh thẻ tín dụng/thanh toán quốc tế (Visa/Mastercard). 
   * *Oracle sẽ trừ khoảng 1-2 USD để xác thực thẻ và hoàn lại tiền ngay lập tức. Bạn sẽ không bị tính phí trừ khi chủ động nâng cấp tài khoản.*
3. Chọn vùng (Home Region) gần Việt Nam nhất (khuyên dùng **Singapore** hoặc **Tokyo** để có đường truyền nhanh nhất).

---

### Bước 2: Tạo Máy Ảo (Compute Instance)
1. Sau khi đăng nhập, truy cập vào menu: **Compute** ➔ **Instances** ➔ Chọn **Create Instance**.
2. **Cấu hình Image and Shape**:
   * Bấm **Edit** ở phần Image and Shape.
   * Chọn hệ điều hành (**Image**): **Ubuntu 22.04 LTS** hoặc **Ubuntu 24.04**.
   * Chọn kiểu máy ảo (**Shape**): Chọn **Ampere** (ARM-based processor) ➔ Tích chọn `VM.Standard.A1.Flex`.
   * Thiết lập cấu hình: **2 OCPUs** và **12 GB RAM** (hoặc chọn tối đa **4 OCPUs và 24 GB RAM**).
3. **Cấu hình Mạng (Networking)**:
   * Để mặc định tạo Virtual Cloud Network (VCN) mới và Subnet công khai (Public Subnet).
4. **Tải khóa SSH (SSH Keys)**:
   * Chọn **Generate a key pair for me** ➔ Bấm **Save Private Key** và **Save Public Key** về máy tính của bạn. *Đây là chìa khóa duy nhất để bạn truy cập vào VPS.*
5. Bấm **Create** và đợi khoảng 1-2 phút để máy ảo chuyển sang trạng thái **Running**. Ghi lại địa chỉ **Public IP Address** của máy ảo.

---

### Bước 3: Cấu hình Tường Lửa (Mở Cổng Kết Nối)
Mặc định Oracle Cloud sẽ chặn tất cả các cổng ngoại trừ cổng SSH (22). Bạn cần mở cổng cho Airflow (`8080`) và FastAPI Web Portal (`8000`).

1. Tại trang chi tiết của máy ảo vừa tạo, phần **Instance details**, click vào tên của Subnet tại mục **Public IP Address / Subnet**.
2. Click vào **Default Security List for...**
3. Bấm **Add Ingress Rules** để tạo 2 quy tắc mở cổng:
   * **Quy tắc 1 (Mở cổng Airflow):**
     * **Source CIDR:** `0.0.0.0/0` (Cho phép mọi IP truy cập).
     * **IP Protocol:** `TCP`.
     * **Destination Port Range:** `8080`.
   * **Quy tắc 2 (Mở cổng Web API):**
     * **Source CIDR:** `0.0.0.0/0`.
     * **IP Protocol:** `TCP`.
     * **Destination Port Range:** `8000`.
4. Bấm **Add Ingress Rules**.

---

### Bước 4: Truy Cập Vào VPS và Cài Đặt Docker

1. Mở Terminal trên máy tính của bạn (CMD hoặc PowerShell trên Windows) và kết nối tới VPS bằng Private Key đã tải ở Bước 2:
   ```bash
   ssh -i "path/to/your/private_key.key" ubuntu@<PUBLIC_IP_CUA_VPS>
   ```
2. Cập nhật hệ thống Ubuntu:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```
3. Cài đặt Docker và Docker Compose:
   ```bash
   # Cài đặt Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   
   # Thêm user hiện tại vào nhóm docker để chạy không cần lệnh sudo
   sudo usermod -aG docker ubuntu
   
   # Khởi động lại terminal hoặc chạy lệnh sau để áp dụng quyền mới
   newgrp docker
   ```

---

### Bước 5: Đẩy Dự Án Lên VPS và Cấu Hình Chạy

1. Nhân bản dự án từ GitHub của bạn về VPS:
   ```bash
   git clone https://github.com/chuong1104/CrawlJobITHaNoi.git
   cd CrawlJobITHaNoi
   ```
2. Thiết lập biến môi trường `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
   * *Nhấn `Ctrl + O` để lưu, `Enter` để xác nhận, và `Ctrl + X` để thoát chỉnh sửa.*
   * **Lưu ý an ninh:** Hãy đổi mật khẩu mặc định của PostgreSQL (`POSTGRES_PASSWORD=airflow`) sang một mật khẩu mạnh để bảo vệ cơ sở dữ liệu khi công khai trên môi trường Internet.
3. Tạo các thư mục phục vụ ghi Log và chứa DB cục bộ:
   ```bash
   mkdir -p logs data data/floci
   ```
4. Build và khởi chạy Docker Compose:
   ```bash
   docker compose build
   docker compose up -d
   ```
5. Thực hiện khởi tạo cơ sở dữ liệu (Database Migrations):
   *(Thực hiện giống như lúc chạy local nhưng đã có cấu hình tự động điền mật khẩu)*
   ```bash
   # Tạo schema silver, indexes và procedures
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/01_create_silver_schema.sql
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/02_create_cdc_tables.sql
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/02_create_indexes.sql
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/03_create_procedures.sql
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/silver/04_create_batch_procedures.sql

   # Tạo tầng Gold DWH
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/gold/01_create_gold_dwh_schema.sql
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/gold/02_create_gold_procedures.sql
   docker compose exec airflow env PGPASSWORD=airflow psql -h postgres -U airflow -d job_scraper_db -f /opt/airflow/scripts/gold/02_create_materialized_views.sql
   ```

---

### Bước 6: Sử Dụng Và Kiểm Tra Kết Quả

Khi các bước trên hoàn tất thành công:
1. **Truy cập Airflow UI:** Mở trình duyệt truy cập: `http://<PUBLIC_IP_CUA_VPS>:8080` (admin/admin). Bật và kiểm tra DAG `daily_job_pipeline`.
2. **Truy cập Web Portal (Nếu đã cài đặt theo tài liệu hướng dẫn 23):** Mở trình duyệt truy cập: `http://<PUBLIC_IP_CUA_VPS>:8000` để sử dụng giao diện tìm kiếm việc làm IT.
3. Nếu bạn muốn cấu hình bảo mật chuyên nghiệp (không cần gõ số cổng `:8080` hay `:8000` mà truy cập bằng tên miền qua HTTPS), bạn hãy tham khảo cấu hình **Nginx Reverse Proxy** và cài đặt **Certbot SSL** miễn phí ở tài liệu tiếp theo.
