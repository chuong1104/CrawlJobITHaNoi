# ============================================================

# Airflow + Playwright + DuckDB + dbt

# ============================================================

FROM apache/airflow:2.10.5-python3.11

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

RUN pip install --no-cache-dir \
    -r /tmp/requirements.txt

# Switch to root to install playwright system dependencies
USER root
RUN python -m playwright install-deps chromium

USER airflow
RUN playwright install chromium

WORKDIR /opt/airflow
