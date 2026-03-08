# Infrastructure - Docker, Environment & Deployment

## Tổng quan

Dự án chạy hoàn toàn trong **Docker containers**, quản lý bằng `docker-compose`. Môi trường bao gồm 5 services chính.

---

## Services

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                          │
│                                                             │
│  ┌─────────────────┐    ┌──────────────────────────────┐   │
│  │    postgres:15  │    │       redis:7.2-alpine        │   │
│  │  Port: 5432     │    │       Port: 6379              │   │
│  └────────┬────────┘    └──────────────┬───────────────┘   │
│           │                            │                   │
│           ▼                            ▼                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │           airflow-webserver  :8080                 │    │
│  │           airflow-scheduler                        │    │
│  │           airflow-worker (Celery)                  │    │
│  │           airflow-init (one-time setup)            │    │
│  │                                                    │    │
│  │   Build từ: ./Dockerfile (custom Airflow image)    │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Services chi tiết

### 1. `postgres` (PostgreSQL 15)
- **Dùng cho:** Airflow metadata DB + Job Scraper Data Warehouse
- **Volume:** `postgres_data` (persistent, không bị xóa khi restart)
- **Port expose:** `5432:5432` (truy cập từ host để debug)
- **Health check:** `pg_isready -U ${POSTGRES_USER}`

### 2. `redis` (Redis 7.2 Alpine)
- **Dùng cho:** Celery message broker (queue các task Airflow)
- **Port:** Internal only (không expose ra host)
- **Health check:** `redis-cli ping`

### 3. `airflow-webserver`
- **Port:** `8080:8080`
- **Truy cập:** http://localhost:8080
- **Mặc định:** user `admin` / pass `admin`
- **Health check:** `GET /health` endpoint

### 4. `airflow-scheduler`
- **Nhiệm vụ:** Scan DAG files, trigger tasks theo schedule
- **Health check:** Port 8974 (Airflow scheduler health endpoint)

### 5. `airflow-worker`
- **Nhiệm vụ:** Nhận task từ Redis queue, thực thi scraping
- **Scale:** Có thể scale horizontally: `docker-compose up --scale airflow-worker=3`

### 6. `airflow-init` (One-time)
- **Nhiệm vụ:** `airflow db migrate` + tạo user admin
- **Restart policy:** `on-failure` (không restart khi thành công)

---

## Dockerfile

```dockerfile
FROM apache/airflow:2.8.1-python3.11

USER root
# Cài system dependencies cho Playwright (Chromium)
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 ...
    && apt-get clean

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
RUN playwright install chromium
```

**Lý do custom image:**
- Base image Airflow không có Playwright/Chromium
- Cần cài thêm `scrapling`, `pydantic v2`, `fake-useragent`, v.v.

---

## Volume mounts

| Host path | Container path | Mô tả |
|---|---|---|
| `./dags` | `/opt/airflow/dags` | DAG files |
| `./logs` | `/opt/airflow/logs` | Airflow task logs |
| `./plugins` | `/opt/airflow/plugins` | Custom operators/hooks |
| `./src` | `/opt/airflow/src` | Business logic (scraper code) |
| `./data` | `/opt/airflow/data` | Raw & processed data |

---

## Biến môi trường (`.env`)

### Database
```bash
POSTGRES_HOST=postgres           # Hostname trong Docker network
POSTGRES_PORT=5432
POSTGRES_DB=job_scraper_db
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow        # ⚠️ Thay bằng password mạnh ở production
```

### Airflow Core
```bash
AIRFLOW__CORE__EXECUTOR=CeleryExecutor
AIRFLOW__CORE__FERNET_KEY=                # Sinh bằng: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true
AIRFLOW__CORE__LOAD_EXAMPLES=false
AIRFLOW_UID=50000                         # UID của user airflow trong container
```

### Proxy (tùy chọn)
```bash
PROXY_URL=http://proxyhost:port
PROXY_USERNAME=your_proxy_user
PROXY_PASSWORD=your_proxy_pass
```

### Google Cloud (tùy chọn)
```bash
GOOGLE_APPLICATION_CREDENTIALS=/opt/airflow/keys/gcp-key.json
BIGQUERY_PROJECT_ID=your-gcp-project
BIGQUERY_DATASET=job_scraper
```

---

## Khởi động dự án

### Lần đầu tiên

```bash
# 1. Clone repo và vào thư mục dự án
cd job_scraper_de_project

# 2. Tạo file .env từ template
cp .env.example .env
# Chỉnh sửa .env với credentials thực tế

# 3. Sinh Fernet key cho Airflow
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy kết quả vào AIRFLOW__CORE__FERNET_KEY trong .env

# 4. Build image và khởi chạy
docker-compose up --build -d

# 5. Kiểm tra tất cả services đang chạy
docker-compose ps

# 6. Xem logs của airflow-init để đảm bảo DB migrate thành công
docker-compose logs airflow-init
```

### Các lần sau

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Restart một service
docker-compose restart airflow-scheduler

# Xem logs realtime
docker-compose logs -f airflow-worker
```

---

## Scale Workers

Khi cần chạy nhiều scraper song song hơn:

```bash
# Scale lên 3 worker
docker-compose up -d --scale airflow-worker=3

# Xem trạng thái
docker-compose ps
```

---

## Troubleshooting

### Container không start được

```bash
# Kiểm tra logs
docker-compose logs postgres
docker-compose logs airflow-webserver

# Kiểm tra health
docker-compose ps
```

### Airflow không thấy DAG

```bash
# Kiểm tra DAG file có lỗi syntax không
docker-compose exec airflow-scheduler python /opt/airflow/dags/etl_job_portals_dag.py

# Reload DAGs thủ công
docker-compose exec airflow-scheduler airflow dags reserialize
```

### Lỗi kết nối Playwright

```bash
# Kiểm tra Chromium đã được cài chưa
docker-compose exec airflow-worker playwright --version

# Cài lại nếu cần
docker-compose exec airflow-worker playwright install chromium
```

### Reset toàn bộ (⚠️ Xóa hết data)

```bash
docker-compose down -v   # -v xóa cả volumes (kể cả postgres_data)
docker-compose up --build -d
```

---

## Cấu hình Production

Khi deploy lên server thực tế, cần thay đổi:

1. **Passwords mạnh** trong `.env`
2. **Fernet key** mới, không để trống
3. **Tắt expose port 5432** của Postgres ra bên ngoài
4. **SSL/TLS** cho Airflow webserver (nginx reverse proxy)
5. **Giới hạn tài nguyên** Docker containers (`mem_limit`, `cpus`)
6. **Backup** volume `postgres_data` định kỳ
7. **Log rotation** cho `logs/` directory

```yaml
# Ví dụ giới hạn tài nguyên trong docker-compose.yml (production):
services:
  airflow-worker:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.5"
```
