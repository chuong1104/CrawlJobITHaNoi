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

# Pre-install pip/setuptools/wheel and browser automation libraries.
# Doing this BEFORE copying requirements.txt allows Docker to cache the heavy browser downloads.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir "playwright>=1.43.0" "patchright>=0.0.1" "browserforge>=1.0.0"

USER root
# Install browser system dependencies (only need to run once, patchright uses same deps)
RUN python -m playwright install-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER airflow
# Download Chromium browsers & update browserforge signatures
RUN playwright install chromium && \
    python -m patchright install chromium && \
    python -m browserforge update

# Copy remaining requirements and install them.
# Any future changes in requirements.txt will only rebuild from here,
# saving you from downloading and configuring Chromium again!
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /opt/airflow



