# Hướng dẫn Bảo trì & Tối ưu Dung lượng Docker trên Windows (WSL2)

Tài liệu này hướng dẫn cách dọn dẹp tài nguyên Docker thừa và thu nhỏ dung lượng file ổ đĩa ảo (`docker_data.vhdx`) trên Windows để giải phóng không gian ổ đĩa host (ví dụ: ổ `D:` hoặc `C:`).

---

## 1. Tại sao ổ đĩa ảo Docker (`.vhdx`) bị phình dung lượng?

Khi chạy Docker Desktop trên Windows thông qua **WSL2 backend**, dữ liệu của toàn bộ containers, volumes, và images được lưu trữ trong một ổ đĩa ảo định dạng **VHDX** (thường là `docker_data.vhdx`).

* **Cơ chế mở rộng động:** File VHDX sẽ tự động phình to ra khi Docker ghi thêm dữ liệu mới.
* **Hạn chế thu nhỏ:** Khi bạn dọn dẹp hoặc xóa dữ liệu bên trong Docker (như xóa container, image), Windows **không tự động giải phóng dung lượng** của file VHDX trên máy host. File này vẫn giữ nguyên dung lượng tối đa đã đạt được.

Để giải quyết triệt để, chúng ta cần thực hiện quy trình 2 bước:
1. **Dọn dẹp dữ liệu rác** bên trong Docker (giải phóng block trống bên trong ổ đĩa ảo).
2. **Nén (Compact)** file `.vhdx` từ phía Windows để trả lại dung lượng cho ổ đĩa vật lý.

---

## 2. Bước 1: Các lệnh dọn dẹp Docker (Docker Cleanup)

Trước khi tiến hành nén ổ đĩa ảo, bạn cần giải phóng tối đa dữ liệu không dùng tới bên trong Docker.

### Dọn dẹp nhanh toàn bộ (Khuyên dùng)

Lệnh này dọn dẹp các containers đã dừng, networks không dùng, images không tên (dangling), và build cache:
```bash
docker system prune
```

Để dọn dẹp **triệt để** (xóa cả các image chưa dùng tới và volumes không gắn kết):
```bash
# CẢNH BÁO: Lệnh này sẽ xóa toàn bộ volumes chưa gắn với container đang chạy
docker system prune -a --volumes
```

### Dọn dẹp chi tiết từng thành phần

#### 1. Dọn dẹp Containers (Bộ lưu trữ tạm của container đã tắt)
```bash
# Xóa tất cả các container đã dừng hoạt động
docker container prune
```

#### 2. Dọn dẹp Images (Các bản đóng gói hệ điều hành/app)
```bash
# Xóa các dangling images (những image không có tag và không được dùng)
docker image prune

# Xóa tất cả các image không có container nào đang sử dụng (kể cả image có tên)
docker image prune -a
```

#### 3. Dọn dẹp Volumes (Dữ liệu persistent lưu trữ)
Dữ liệu trong Volume thường là database hoặc cấu hình, hãy cẩn thận trước khi xóa.
```bash
# Xóa toàn bộ volumes không được sử dụng bởi bất kỳ container nào
docker volume prune
```

#### 4. Dọn dẹp Build Cache (Bộ nhớ đệm khi build Dockerfile)
Build cache thường chiếm dung lượng rất lớn sau nhiều lần build lại image.
```bash
# Dọn dẹp cache của trình build (BuildKit)
docker builder prune
```

---

## 3. Bước 2: Thu nhỏ (Compact) file ổ đĩa ảo `.vhdx`

Sau khi đã giải phóng dữ liệu bên trong Docker, hãy tiến hành nén file `.vhdx` theo các bước sau:

### 1. Tắt hoàn toàn Docker và WSL2
Để tránh lỗi khóa file (file in use), bạn phải đóng Docker Desktop và tắt dịch vụ WSL.

1. Click chuột phải vào icon Docker Desktop dưới thanh Taskbar -> Chọn **Quit Docker Desktop**.
2. Mở một cửa sổ **PowerShell** hoặc **Command Prompt (CMD)** bình thường và chạy lệnh:
   ```powershell
   wsl --shutdown
   ```

### 2. Thực hiện nén bằng công cụ `diskpart`

Mở **PowerShell với quyền Administrator** (Run as Administrator) và thực hiện các lệnh sau:

```powershell
# Khởi chạy trình quản lý ổ đĩa ảo
diskpart
```

Giao diện `diskpart` sẽ hiện lên. Nhập lần lượt các lệnh sau:

```powershell
# 1. Chọn đường dẫn tới file vhdx của Docker (thay đổi đường dẫn phù hợp với máy của bạn)
select vdisk file="D:\DockerData\DockerDesktopWSL\disk\docker_data.vhdx"

# 2. Gắn kết ổ đĩa ảo ở chế độ chỉ đọc để đảm bảo an toàn dữ liệu
attach vdisk readonly

# 3. Quét các block trống và tiến hành nén file vhdx
compact vdisk

# 4. Ngắt gắn kết ổ đĩa ảo sau khi hoàn thành
detach vdisk

# 5. Thoát diskpart
exit
```

### Giải thích các câu lệnh `diskpart`:
* **`select vdisk`**: Định vị đúng file `.vhdx` cần xử lý trên ổ đĩa vật lý của bạn.
* **`attach vdisk readonly`**: Gắn đĩa ảo vào Windows dưới quyền Read-only. Điều này bắt buộc vì lệnh `compact` yêu cầu đĩa ảo phải ở trạng thái được gắn kết và không bị ghi dữ liệu.
* **`compact vdisk`**: Thực hiện thu hồi các block trống vật lý, giảm dung lượng file `.vhdx` về đúng dung lượng thực tế đang dùng của Docker.
* **`detach vdisk`**: Ngắt kết nối ổ đĩa ảo để trả lại quyền kiểm soát cho WSL/Docker khi khởi động lại.
* **`exit`**: Thoát diskpart

---

## 4. Tối ưu hóa Docker Image & Tốc độ Build (Build Cache Optimization)

### Vấn đề gặp phải trước đây
* Quá trình build Dockerfile chứa các thư viện cào dữ liệu nâng cao (`playwright`, `patchright`, `browserforge`) và trình duyệt Chromium đi kèm diễn ra rất lâu.
* Mỗi khi tệp `requirements.txt` có thay đổi nhỏ (như thêm thư viện kiểm thử `pytest`), Docker Engine sẽ xóa cache của tất cả các bước phía sau, dẫn tới việc tải lại toàn bộ trình duyệt Chromium và chạy lại các gói hệ thống từ đầu (tốn thời gian từ 3 - 5 phút và tiêu thụ hàng trăm MB băng thông).

### Giải pháp tối ưu hóa
Dockerfile của dự án đã được cải tiến cấu trúc để phân lớp cache hiệu quả:
1. **Pre-install các gói cốt lõi:** Cài đặt các thư viện `playwright`, `patchright`, và `browserforge` trực tiếp thông qua một lớp build cố định trước khi sao chép toàn bộ `requirements.txt`.
2. **Tải trình duyệt trước:** Thực hiện lệnh tải Chromium (`playwright install chromium` và `patchright install chromium`) ở giai đoạn đầu để Docker lưu trữ vĩnh viễn (cache) các file nhị phân trình duyệt này.
3. **Loại bỏ trùng lặp:** Chỉ chạy `playwright install-deps` một lần duy nhất thay vì chạy cả `patchright install-deps` (do chúng sử dụng chung cấu trúc Chromium).
4. **Copy requirements.txt sau cùng:** File `requirements.txt` và các gói Python thông thường được copy và cài đặt ở lớp cuối. Khi bạn thay đổi file requirements này, Docker sẽ chỉ chạy lại bước cài đặt các gói Python mới mà không cần chạm đến phần trình duyệt Chromium khổng lồ.
5. **Cấu hình .dockerignore:** Chỉ gửi file `requirements.txt` làm build context thay vì gửi toàn bộ thư mục dữ liệu cào khổng lồ (`data/`), giúp tăng tốc độ gửi context lên 0.0s.

---

## 5. Giới hạn tài nguyên (Resource Constraints) & Logs Rotation cho Docker Compose

Để đảm bảo máy tính cá nhân của bạn không bị quá tải khi chạy các luồng dữ liệu lớn, các tối ưu hóa sau đã được áp dụng trong [docker-compose.yml](file:///d:/JobITVN/job_scraper_de_project/docker-compose.yml):

### 5.1 Giới hạn tài nguyên Container Airflow
Khi Airflow chạy tác vụ cào dữ liệu (`crawl_all_sources`), nó sẽ khởi chạy song song 4 workers, tương đương với 4 tiến trình Chromium cùng chạy. Điều này có thể khiến CPU/RAM của laptop bị quá tải.
Chúng ta đã giới hạn tài nguyên tối đa cho container `airflow`:
```yaml
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 6G
        reservations:
          memory: 1G
```
* **Limits:** Giới hạn tối đa container không được dùng vượt quá 4 CPU cores và 6GB RAM, tránh làm đơ hệ điều hành host.
* **Reservations:** Đảm bảo hệ thống cấp phát sẵn tối thiểu 1GB RAM cho container hoạt động ổn định.

### 5.2 Xoay vòng Logs (Log Rotation) để chống tràn đĩa cứng
Mặc định logs in ra màn hình của các container sẽ được lưu trữ vô thời hạn. Với các logs dày đặc từ Scrapers và Airflow, dung lượng file log có thể lên tới hàng chục GB.
Chúng ta đã cấu hình chính sách xoay vòng logs mặc định cho toàn bộ các dịch vụ:
```yaml
x-logging: &default-logging
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
```
Mỗi container chỉ lưu tối đa 3 file logs, dung lượng tối đa mỗi file là 10MB (tối đa 30MB/container).

### 5.3 Tối ưu hóa CPU & RAM chạy ngầm (Idle) của Apache Airflow
Mặc định, Apache Airflow được thiết kế cho hệ thống phân tán Enterprise, nó sẽ khởi chạy rất nhiều tiến trình chạy ngầm để quét DAG liên tục và phục vụ WebServer. Điều này tiêu tốn nhiều RAM và làm CPU luôn ở trạng thái hoạt động trên máy cá nhân.
Chúng ta đã cấu hình tối ưu các biến môi trường trong `docker-compose.yml` để Airflow chạy nhẹ nhàng nhất có thể:
* **`AIRFLOW__WEBSERVER__WORKERS: 1`:** Mặc định Airflow khởi tạo 4 workers Gunicorn chạy ngầm để phục vụ giao diện Web. Việc giảm xuống còn 1 worker giúp giảm ngay lập tức 3 tiến trình Python dư thừa (tiết kiệm **200MB - 400MB RAM**).
* **`AIRFLOW__SCHEDULER__PARSING_PROCESSES: 1`:** Giảm tiến trình parse DAG song song xuống còn 1 để tiết kiệm CPU/RAM (giảm thêm khoảng **150MB RAM**).
* **`AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL: 60` & `AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL: 60`:** Tăng chu kỳ quét thư mục DAGs và parse lại DAGs từ 5-30 giây mặc định lên 60 giây. Điều này giúp giảm tải hoàn toàn CPU lúc rảnh rỗi (giảm tỷ lệ sử dụng CPU chạy ngầm xuống gần 0%).

---

## 6. Tối ưu cấu hình PostgreSQL DWH (ETL Performance Tuning)

Vì dự án chạy các mô hình biến đổi dữ liệu lớn qua dbt và chạy stored procedures để đồng bộ tầng Silver sang Gold DWH trực tiếp trên PostgreSQL, cấu hình mặc định (vốn chỉ dành cho máy cấu hình siêu yếu) đã được nâng cấp trong `docker-compose.yml`:

```yaml
    command: postgres -c shared_buffers=512MB -c work_mem=32MB -c maintenance_work_mem=128MB -c effective_cache_size=1GB -c random_page_cost=1.1
```
* **`shared_buffers=512MB`:** Tăng bộ nhớ đệm cho dữ liệu và chỉ mục, giúp PostgreSQL giảm thiểu số lần phải đọc ghi trực tiếp từ đĩa cứng.
* **`work_mem=32MB`:** Tăng dung lượng bộ nhớ dùng cho các tác vụ sắp xếp (`SORT`) và ghép nối (`JOIN`) phức tạp, giúp các truy vấn dbt và ETL chạy nhanh hơn.
* **`maintenance_work_mem=128MB`:** Tăng tốc độ tạo chỉ mục (index) và thực thi dọn dẹp bảng (`VACUUM`).

---

## 7. Tích hợp AWS S3/Floci và AWS CLI / awslocal

### 7.1 Tự động hóa Khởi tạo Buckets trên S3 Floci
Không cần phải chạy các script thủ công sau khi khởi động Docker, bucket `jobit-bronze`, `jobit-silver` và `jobit-gold` sẽ được tạo tự động thông qua container `airflow-init`:
1. Container `airflow-init` sẽ đợi cho đến khi dịch vụ `floci` S3 (cổng 4566) mở và chấp nhận kết nối.
2. Thực thi mã nguồn Python để kiểm tra và tự động khởi tạo 3 buckets lưu trữ Lakehouse.

### 7.2 Sử dụng AWS CLI và `awslocal` trực tiếp từ Container
Chúng ta đã tích hợp gói `awscli` và `awscli-local` (`awslocal`) vào Docker image của Airflow. Biến môi trường `LOCALSTACK_HOST: floci` được định cấu hình tự động.
Bạn có thể truy cập trực tiếp vào Terminal của container `airflow` để quản trị S3 Mock mà không cần truyền tham số endpoint:

* **Liệt kê danh sách bucket:**
  ```bash
  docker compose exec airflow awslocal s3 ls
  ```
* **Liệt kê các tệp tin trong Bronze Layer:**
  ```bash
  docker compose exec airflow awslocal s3 ls s3://jobit-bronze --recursive
  ```
* **Kiểm tra dữ liệu phân tích Gold Layer:**
  ```bash
  docker compose exec airflow awslocal s3 ls s3://jobit-gold --recursive
  ```
