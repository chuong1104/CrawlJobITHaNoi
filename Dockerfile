# ============================================================
# Dockerfile — Optimized Multi-stage Build (v3.0 Ultra-Slim)
# ============================================================

# ──────────────────────────────────────────────────────────────
# Stage 1: Builder — compile wheels & native C extensions
# ──────────────────────────────────────────────────────────────
FROM apache/airflow:2.10.5-python3.11 AS builder

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        curl \
        wget \
        git \
        libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER airflow

# Cài đặt Python packages vào ~/.local
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ──────────────────────────────────────────────────────────────
# Stage 2: Runtime — gọn nhẹ, bảo mật, tối ưu RAM & Disk
# ──────────────────────────────────────────────────────────────
FROM apache/airflow:2.10.5-python3.11 AS runtime

USER root

# Chỉ cài system libraries thiết yếu ở runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        libgomp1 \
        curl \
        wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy packages đã build từ Stage 1
COPY --chown=airflow:0 --from=builder /home/airflow/.local /home/airflow/.local

# Cài system dependencies cho Chromium headless
RUN /home/airflow/.local/bin/playwright install-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER airflow

# Cài đặt browser Chromium và browserforge definitions
# Dùng cờ --with-deps=false vì apt-deps đã được root cài ở trên
RUN playwright install chromium && \
    python -m browserforge update && \
    rm -rf /home/airflow/.cache/pip

WORKDIR /opt/airflow

# Healthcheck tiết kiệm CPU: tăng start-period và interval hợp lý
HEALTHCHECK --interval=45s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

