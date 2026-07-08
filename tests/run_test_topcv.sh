#!/bin/bash
# Script chạy thử luồng cho riêng TopCV từ Cào -> Bronze -> Staging/Silver -> Gold (Parquet/S3)
# Chạy xuyên qua Docker Container (Airflow) để đảm bảo có đủ thư viện

set -e  # Dừng ngay khi có lệnh thất bại

# cd về thư mục gốc của project
cd "$(dirname "$0")/.."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TOPCV PIPELINE TEST (QUA DOCKER)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Kiểm tra xem Docker có đang chạy không
if ! docker compose ps | grep -q airflow; then
    echo "⚠️ Lỗi: Airflow container chưa chạy. Bạn cần chạy 'docker compose up -d' trước."
    exit 1
fi

# ── Bước 0: Đảm bảo bucket S3 tồn tại ──────────────────────────────────────
echo ""
echo "0. Khởi tạo S3 buckets nếu chưa có..."
docker compose exec airflow bash -c "aws s3 mb s3://jobit-bronze --endpoint-url=http://floci:4566 2>/dev/null || true"
docker compose exec airflow bash -c "aws s3 mb s3://jobit-gold   --endpoint-url=http://floci:4566 2>/dev/null || true"
echo "   ✔ s3://jobit-bronze  s3://jobit-gold  sẵn sàng."

# ── Bước 1: Cào TopCV và lưu vào Bronze (S3 + Local) ───────────────────────
echo ""
echo "1. [SKIPPED] Cào dữ liệu TopCV (đã có sẵn trong Bronze)..."
# docker compose exec airflow bash -c "
# cd /opt/airflow
# python -c \"
# from src.extract.job_online.topcv import TopCVScraper
# print('   Khởi tạo TopCV Scraper...')
# scraper = TopCVScraper()
# print('   Đang cào dữ liệu (giới hạn 1 trang để test)...')
# jobs = scraper.run(pages=1)
# print(f'   ✔ Đã cào và lưu {len(jobs)} jobs vào Bronze.')
# \"
# "

# ── Bước 2: dbt DuckDB (Bronze → Staging → Intermediate) ────────────────────
echo ""
echo "2. Chạy dbt (Staging → Intermediate)..."
docker compose exec airflow bash -c "
set -x
cd /opt/airflow/dbt_jobitvn
which dbt || echo 'dbt not found in PATH'
dbt --version || echo 'dbt version check failed'
dbt run --profiles-dir . --target duckdb_dev --select staging intermediate || echo \"dbt run failed with exit code \$?\"
"

# ── Bước 2.5: Python Sync Engine (Intermediate → Silver) ──────────────────
echo ""
echo "2.5. Chạy Sync Engine nạp vào PostgreSQL Silver..."
docker compose exec airflow bash -c "
cd /opt/airflow
export POSTGRES_HOST=postgres
export PYTHONPATH=/opt/airflow
python src/silver/sync_engine.py
"

# ── Bước 2.7: dbt Postgres (Silver → Warehouse → Mart BI) ─────────────────
echo ""
echo "2.7. Chạy dbt (Warehouse → Mart BI)..."
docker compose exec airflow bash -c "
set -x
cd /opt/airflow/dbt_jobitvn
dbt run --profiles-dir . --target pg_dev --select warehouse marts || echo \"dbt run failed with exit code \$?\"
"

# ── Bước 3: Gold Export (DuckDB → Parquet → S3) ─────────────────────────────
echo ""
echo "3. Chạy Gold Exporter (Silver → Parquet → s3://jobit-gold/)..."
docker compose exec airflow bash -c "
cd /opt/airflow
export POSTGRES_HOST=postgres
python src/gold/gold_exporter.py
"

# ── Bước 4: Kiểm tra kết quả trên S3 ────────────────────────────────────────
echo ""
echo "4. Kết quả trên S3 (jobit-gold):"
docker compose exec airflow bash -c "
aws s3 ls s3://jobit-gold/ --recursive --endpoint-url=http://floci:4566 --human-readable --summarize
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✔ Hoàn tất luồng kiểm thử TopCV!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
