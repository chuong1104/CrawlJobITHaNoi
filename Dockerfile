# ============================================================
# Dockerfile — Single-Stage Optimized (Chống OOM trên WSL2 / Docker Desktop)
# ============================================================
FROM apache/airflow:2.10.5-python3.11

USER root

# 1. Cài đặt build tools & system libraries thiết yếu
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        git \
        libpq-dev \
        libpq5 \
        libgomp1 \
        curl \
        wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER airflow

# 2. Cài đặt Python packages trực tiếp vào ~/.local
# (Không dùng multi-stage COPY để loại bỏ 100% rủi ro OOM do tar stream)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

USER root

# 3. Gỡ bỏ build tools để giữ image gọn nhẹ, giữ lại runtime libs (libpq5, libgomp1)
RUN apt-get purge -y --auto-remove build-essential gcc g++ git libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 4. Cài system dependencies cho Chromium headless
RUN /home/airflow/.local/bin/playwright install-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER airflow

# 5. Cài đặt browser Chromium và browserforge definitions
RUN playwright install chromium && \
    python -m browserforge update && \
    rm -rf /home/airflow/.cache/pip

WORKDIR /opt/airflow

# Healthcheck tiết kiệm CPU
HEALTHCHECK --interval=45s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
