# ============================================================
# Dockerfile - Custom Airflow image
# Base: apache/airflow:2.8.1-python3.11
# Thêm: Scrapling, Playwright, BeautifulSoup, pandas, pydantic
# ============================================================

FROM apache/airflow:2.8.1-python3.11

USER root

# Cài system dependencies cho Playwright (headless Chromium)
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

# Cài Python packages
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Cài Playwright browsers (Chromium)
RUN playwright install chromium
