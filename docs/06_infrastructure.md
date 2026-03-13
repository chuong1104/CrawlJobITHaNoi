# 06 — Infrastructure — Docker, Environment & Deployment

> **Cập nhật:** 2026-03-11 | Phiên bản: 2.0  
> Cập nhật infrastructure để hỗ trợ toàn bộ stack JobInsight Platform: bổ sung pgvector extension cho PostgreSQL, service FastAPI backend, service Next.js frontend, và cấu hình cho NLP processing với model download.

---

## Tổng quan

Dự án chạy hoàn toàn trong Docker containers, quản lý bằng `docker-compose`. Toàn bộ stack được chia thành ba nhóm service: Data Pipeline (Airflow + PostgreSQL + Redis), NLP Services (model serving), và Web Application (FastAPI + Next.js).

---

## Sơ đồ Services

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Docker Network: jobinsight                   │
│                                                                      │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐   │
│  │  postgres:15-pgvector    │    │      redis:7.2-alpine         │   │
│  │  Port: 5432              │    │      Port: 6379               │   │
│  │  + pgvector extension    │    │      (internal only)          │   │
│  └──────────┬───────────────┘    └──────────────┬───────────────┘   │
│             │                                    │                  │
│             ▼                                    ▼                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    AIRFLOW SERVICES                          │   │
│  │  airflow-webserver  :8080                                    │   │
│  │  airflow-scheduler                                           │   │
│  │  airflow-worker (Celery) — có thể scale                     │   │
│  │  airflow-init (one-time)                                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  WEB APPLICATION SERVICES                    │   │
│  │  api-backend  :8000  (FastAPI)      [Giai đoạn 3]           │   │
│  │  web-frontend :3000  (Next.js)      [Giai đoạn 3]           │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Services Chi tiết

### 1. `postgres` (PostgreSQL 15 + pgvector)

Image sử dụng: `pgvector/pgvector:pg15` thay vì `postgres:15` vanilla, để có sẵn extension pgvector cho vector search.

**Cấu hình quan trọng:**
- Volume: `postgres_data` (persistent)
- Port expose: `5432:5432` (có thể tắt ở production)
- Shared buffers: tăng lên 256MB cho hiệu suất query tốt hơn
- Max connections: 200 (hỗ trợ nhiều Airflow workers + API connections)
- Health check: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`

**Init script:** `docker-entrypoint-initdb.d/01_init.sql` chạy tự động khi container khởi tạo lần đầu, tạo extension `vector` và extension `pg_trgm` (hỗ trợ fuzzy text search).

### 2. `redis` (Redis 7.2 Alpine)

Phục vụ hai mục đích: Celery message broker cho Airflow workers, và cache layer cho FastAPI backend (cache kết quả search, session data, recommendation results).

**Cấu hình:** Port chỉ expose internal trong Docker network. Maxmemory policy: `allkeys-lru` (tự động xóa key ít dùng nhất khi đầy bộ nhớ).

### 3. `airflow-webserver`

- Port: `8080:8080`
- Truy cập: http://localhost:8080
- Credentials mặc định: admin/admin
- Health check: `GET /health`

### 4. `airflow-scheduler`

Scan DAG files mỗi 30 giây. Health check qua port 8974.

### 5. `airflow-worker`

Nhận task từ Redis queue, thực thi scraping và NLP processing. Khi chạy NLP tasks nặng (embedding), worker cần đủ RAM để load model (~2GB cho multilingual-e5-base).

Scale horizontally: `docker-compose up -d --scale airflow-worker=3`

**Lưu ý:** Khi scale lên nhiều workers, cần đảm bảo model NLP chỉ được load một lần và chia sẻ giữa các workers thay vì mỗi worker load riêng. Sử dụng model serving pattern hoặc shared memory.

### 6. `airflow-init` (One-time)

`airflow db migrate` + tạo user admin + chạy `create_tables.sql`. Restart policy: `on-failure`.

### 7. `api-backend` (FastAPI — Giai đoạn 3)

```yaml
api-backend:
  build: ./app/backend
  ports: ["8000:8000"]
  depends_on: [postgres, redis]
  volumes:
    - ./app/backend:/app
  environment:
    - DATABASE_URL=postgresql://...
    - REDIS_URL=redis://redis:6379
    - SECRET_KEY=${API_SECRET_KEY}
  command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 8. `web-frontend` (Next.js — Giai đoạn 3)

```yaml
web-frontend:
  build: ./app/frontend
  ports: ["3000:3000"]
  depends_on: [api-backend]
  environment:
    - NEXT_PUBLIC_API_URL=http://api-backend:8000
  command: npm run dev
```

---

## Dockerfile

```dockerfile
FROM apache/airflow:2.8.1-python3.11

USER root
# System dependencies cho Playwright (Chromium) và NLP
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 \
    # Build tools cho một số Python packages
    gcc g++ \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Cài Playwright browsers
RUN playwright install chromium

# Pre-download NLP model để tránh download lại mỗi lần chạy
# (Comment out nếu muốn download lazy)
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('intfloat/multilingual-e5-base')"
```

**Lưu ý về NLP model:** Model `multilingual-e5-base` có kích thước ~280MB. Pre-download vào Docker image làm tăng image size nhưng tránh download runtime. Có thể mount model từ host volume thay thế.

---

## Volume Mounts

| Host Path | Container Path | Mô tả |
|---|---|---|
| `./dags` | `/opt/airflow/dags` | DAG files |
| `./logs` | `/opt/airflow/logs` | Airflow task logs |
| `./plugins` | `/opt/airflow/plugins` | Custom operators |
| `./src` | `/opt/airflow/src` | Business logic |
| `./data` | `/opt/airflow/data` | Raw & processed data |
| `./models` | `/opt/airflow/models` | NLP models cache (optional) |
| `postgres_data` | `/var/lib/postgresql/data` | PostgreSQL data (named volume) |

---

## Biến Môi trường (`.env`)

### Database
```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=job_scraper_db
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow        # Thay bằng password mạnh ở production
```

### Airflow Core
```bash
AIRFLOW__CORE__EXECUTOR=CeleryExecutor
AIRFLOW__CORE__FERNET_KEY=                # Sinh bằng script Fernet
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true
AIRFLOW__CORE__LOAD_EXAMPLES=false
AIRFLOW_UID=50000

# Tăng giới hạn bộ nhớ cho NLP workers
AIRFLOW__CELERY__WORKER_CONCURRENCY=4
```

### Web Application
```bash
API_SECRET_KEY=                           # Random 32-byte hex
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### NLP Configuration
```bash
EMBEDDING_MODEL=intfloat/multilingual-e5-base
MODELS_CACHE_DIR=/opt/airflow/models
HF_HOME=/opt/airflow/models              # HuggingFace cache dir
```

### Proxy (Tùy chọn)
```bash
PROXY_URL=http://proxyhost:port
PROXY_USERNAME=your_proxy_user
PROXY_PASSWORD=your_proxy_pass
```

### Google Cloud (Tùy chọn)
```bash
GOOGLE_APPLICATION_CREDENTIALS=/opt/airflow/keys/gcp-key.json
BIGQUERY_PROJECT_ID=your-gcp-project
BIGQUERY_DATASET=job_scraper
```

### Notifications (Tùy chọn)
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

---

## Khởi động Dự án

### Lần Đầu Tiên

```bash
# 1. Clone repo
cd jobinsight_platform

# 2. Tạo .env
cp .env.example .env
# Chỉnh sửa .env với credentials thực tế

# 3. Sinh Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy vào AIRFLOW__CORE__FERNET_KEY

# 4. Tạo thư mục cần thiết
mkdir -p data/raw data/processed logs models

# 5. Build và khởi chạy (chỉ Data Pipeline trước)
docker-compose up --build -d postgres redis airflow-init
docker-compose logs -f airflow-init  # Chờ đến khi thấy "Done"

# 6. Khởi chạy Airflow services
docker-compose up -d airflow-webserver airflow-scheduler airflow-worker

# 7. Kiểm tra
docker-compose ps
# Truy cập http://localhost:8080 (admin/admin)
```

### Khởi chạy Web App (Giai đoạn 3)

```bash
docker-compose up -d api-backend web-frontend
# API: http://localhost:8000/docs
# Frontend: http://localhost:3000
```

### Các Lệnh Thường Dùng

```bash
# Start tất cả
docker-compose up -d

# Stop tất cả
docker-compose down

# Restart một service
docker-compose restart airflow-scheduler

# Xem logs realtime
docker-compose logs -f airflow-worker

# Scale workers
docker-compose up -d --scale airflow-worker=3

# Truy cập DB trực tiếp
docker-compose exec postgres psql -U airflow -d job_scraper_db
```

---

## Troubleshooting

### Container Không Start

```bash
docker-compose logs postgres
docker-compose logs airflow-webserver
docker-compose ps
```

### Airflow Không Thấy DAG

```bash
# Kiểm tra syntax DAG file
docker-compose exec airflow-scheduler python /opt/airflow/dags/etl_job_portals_dag.py

# Reserialize DAGs
docker-compose exec airflow-scheduler airflow dags reserialize
```

### Lỗi pgvector

```bash
# Kiểm tra extension đã được tạo chưa
docker-compose exec postgres psql -U airflow -d job_scraper_db -c "\dx"
# Phải thấy "vector" trong danh sách

# Tạo extension thủ công nếu cần
docker-compose exec postgres psql -U airflow -d job_scraper_db -c "CREATE EXTENSION vector;"
```

### Lỗi NLP Model Không Download Được

```bash
# Kiểm tra network từ trong container
docker-compose exec airflow-worker curl -I https://huggingface.co

# Download thủ công vào volume
docker-compose exec airflow-worker python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"
```

### Lỗi Playwright

```bash
# Kiểm tra Chromium
docker-compose exec airflow-worker playwright --version

# Cài lại
docker-compose exec airflow-worker playwright install chromium
```

### Reset Hoàn toàn (⚠️ Xóa hết data)

```bash
docker-compose down -v  # -v xóa cả named volumes
docker-compose up --build -d
```

---

## Cấu hình Production

Khi deploy lên server thực tế, cần thay đổi:

**Bảo mật:**
- Passwords mạnh (≥ 20 ký tự random) trong `.env`
- Fernet key mới, không commit vào git
- Tắt expose port 5432 và 6379 ra bên ngoài
- SSL/TLS cho Airflow webserver và API backend qua nginx reverse proxy
- Rate limiting cho API endpoints

**Hiệu suất:**
- Tăng `AIRFLOW__CELERY__WORKER_CONCURRENCY` phù hợp với số CPU
- Tăng PostgreSQL `shared_buffers` lên 25% RAM server
- Cấu hình Redis `maxmemory` phù hợp
- Giới hạn tài nguyên Docker containers:

```yaml
services:
  airflow-worker:
    deploy:
      resources:
        limits:
          memory: 4G    # Cần đủ RAM cho NLP model
          cpus: "2.0"
  postgres:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.0"
```

**Vận hành:**
- Backup volume `postgres_data` hàng ngày (pg_dump)
- Log rotation cho `logs/` directory (giữ 30 ngày)
- Health check endpoint monitoring (Uptime Kuma hoặc tương đương)
- Alerting cho container down qua Slack/email
