"""
daily_pipeline.py — Airflow DAG: pipeline hàng ngày cho toàn bộ job portals.

Flow: start → crawl_all_sources → run_dbt_staging → sync_silver_layer → run_gold_dwh → export_gold_marts → end
Schedule: 6h sáng mỗi ngày (Asia/Ho_Chi_Minh)
"""
import json
import subprocess
import time
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


# ---------------------------------------------------------------------------
# Task 1: crawl_all_sources — chạy scraper và đẩy metrics lên XCom
# ---------------------------------------------------------------------------
def _crawl_and_push_metrics(**kwargs) -> dict:
    """
    Chạy run_scrapers.py, parse stdout để lấy metrics, push lên XCom.
    Metrics schema:
        success_count, failed_count, total_records, duration_seconds, scrapers: list[dict]
    """
    ti = kwargs["ti"]
    t0 = time.monotonic()

    result = subprocess.run(
        [
            "python",
            "/opt/airflow/scripts/run_scrapers.py",
            "--mode", "full",
            "--workers", "4",
        ],
        capture_output=True,
        text=True,
        timeout=3600,  # 60 minutes
    )

    duration = time.monotonic() - t0
    stdout   = result.stdout or ""
    stderr   = result.stderr or ""

    # ----- Parse metrics từ stdout -----
    success_count = 0
    failed_count  = 0
    total_records = 0
    scraper_rows: list[dict] = []

    for line in stdout.splitlines():
        if "✔ ok" in line or "✖ fail" in line:
            parts = line.split()
            try:
                name    = next((p for p in parts if p.isalpha() and len(p) > 2), "")
                status  = "ok" if "✔ ok" in line else "fail"
                records = int(next((p for p in parts if p.isdigit()), 0))
                scraper_rows.append({"name": name, "status": status, "records": records})
                if status == "ok":
                    success_count += 1
                    total_records += records
                else:
                    failed_count += 1
            except (ValueError, StopIteration):
                pass

    metrics = {
        "run_date":       datetime.utcnow().isoformat(),
        "success_count":  success_count,
        "failed_count":   failed_count,
        "total_records":  total_records,
        "duration_secs":  round(duration, 1),
        "exit_code":      result.returncode,
        "scrapers":       scraper_rows,
    }

    ti.xcom_push(key="scraper_metrics", value=metrics)

    print("=" * 60)
    print("  SCRAPER METRICS")
    print("=" * 60)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print("=" * 60)

    if stderr:
        print("\n--- STDERR (errors only) ---")
        for ln in stderr.splitlines():
            if any(k in ln.upper() for k in ("ERROR", "CRITICAL", "EXCEPTION", "TRACEBACK")):
                print(ln)

    if result.returncode != 0:
        raise RuntimeError(
            f"run_scrapers.py exited with code {result.returncode}. "
            f"failed_count={failed_count}"
        )

    return metrics


with DAG(
    "daily_job_pipeline",
    default_args=default_args,
    description="Daily pipeline: Extract job postings → Bronze → dbt Transform → Silver → Gold",
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["jobitvn", "elt", "end-to-end"],
) as dag:

    start = EmptyOperator(task_id="start")

    crawl_all_sources = PythonOperator(
        task_id="crawl_all_sources",
        python_callable=_crawl_and_push_metrics,
        execution_timeout=timedelta(minutes=70),
        doc_md="Chạy toàn bộ scrapers song song và push metrics lên XCom",
    )

    # ── Task 2: dbt (Staging) ────────────────
    run_dbt_staging = BashOperator(
        task_id="run_dbt_staging",
        bash_command=(
            "dbt run "
            "--select staging intermediate "
            "--profiles-dir /opt/airflow/dbt "
            "--project-dir /opt/airflow/dbt_jobitvn"
        ),
        doc_md="Chạy dbt models cho tầng Staging và Intermediate (DuckDB).",
    )

    # ── Task 3: Sync Silver Layer ───────────────────────
    def _sync_silver_layer(**kwargs):
        """Khởi tạo SilverSyncEngine và JobDedupEngine để nạp vào DB 3NF"""
        import sys
        import time
        from datetime import datetime
        sys.path.insert(0, "/opt/airflow")
        
        from src.silver.sync_engine import SilverSyncEngine
        from src.silver.dedup_engine import JobDedupEngine
        
        # Tạo session_id theo timestamp
        session_id = int(time.time())
        session_start_time = datetime.utcnow().isoformat()
        
        # 1. Sync Jobs
        sync_engine = SilverSyncEngine(duckdb_path="/opt/airflow/data/jobitvn.duckdb")
        sync_engine.connect()
        try:
            sync_engine.sync_staged_jobs(session_id=session_id)
            # Run lifecycle auto-close cho các sources phổ biến
            for src_id in range(1, 12):
                sync_engine.run_lifecycle_checks(source_id=src_id, session_id=session_id, session_start_time=session_start_time)
        finally:
            sync_engine.close()
            
        # 2. Dedup
        dedup_engine = JobDedupEngine()
        dedup_engine.connect()
        try:
            dedup_engine.run_dedup_pipeline(session_id=session_id)
        finally:
            dedup_engine.close()
            
        return {"session_id": session_id, "status": "success"}

    sync_silver_layer = PythonOperator(
        task_id="sync_silver_layer",
        python_callable=_sync_silver_layer,
        execution_timeout=timedelta(minutes=30),
        doc_md="Sync dữ liệu từ DuckDB Staging vào PostgreSQL Silver (chống N+1, cập nhật SCD, TF-IDF dedup).",
    )

    # ── Task 4: Run Gold DWH ───────────────────────
    def _run_gold_dwh(**kwargs):
        """Gọi SQL Procedures để đồng bộ Silver sang Gold DWH"""
        import sys
        sys.path.insert(0, "/opt/airflow")
        
        from src.gold.gold_exporter import GoldExporter
        exporter = GoldExporter(output_dir="/opt/airflow/data")
        exporter.connect()
        try:
            exporter.run_dwh_sync()
        finally:
            exporter.close()
            
        return {"status": "success"}

    run_gold_dwh = PythonOperator(
        task_id="run_gold_dwh",
        python_callable=_run_gold_dwh,
        execution_timeout=timedelta(minutes=15),
        doc_md="Nạp dữ liệu vào schema DWH và refresh materialized view API.",
    )

    # ── Task 5: Export Gold Marts ───────────────────────
    def _export_gold_marts(**kwargs):
        """Export Data Marts sang Parquet"""
        import sys
        sys.path.insert(0, "/opt/airflow")
        
        from src.gold.gold_exporter import GoldExporter
        exporter = GoldExporter(output_dir="/opt/airflow/data")
        exporter.connect()
        try:
            exporter.export_mart_bi()
            exporter.export_mart_ml()
        finally:
            exporter.close()
            
        return {"status": "success"}

    export_gold_marts = PythonOperator(
        task_id="export_gold_marts",
        python_callable=_export_gold_marts,
        execution_timeout=timedelta(minutes=20),
        doc_md="Dùng DuckDB đọc DWH và ghi ra Parquet cho Power BI và AI/ML.",
    )

    end = EmptyOperator(task_id="end")

    # Workflow dependencies (DAG Graph)
    start >> crawl_all_sources >> run_dbt_staging >> sync_silver_layer >> run_gold_dwh >> export_gold_marts >> end
