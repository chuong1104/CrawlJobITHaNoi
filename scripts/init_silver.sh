#!/bin/bash
export PGPASSWORD=airflow
for f in /opt/airflow/scripts/sql/silver/*.sql; do
    echo "Running $f"
    psql -h postgres -U airflow -d job_scraper_db -f "$f"
done
