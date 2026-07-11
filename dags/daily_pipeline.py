"""
daily_pipeline.py — Airflow DAG: pipeline hàng ngày cho toàn bộ job portals.

Flow:
  start
    → crawl_all_sources       (Extract: cào và ghi Delta Bronze)
    → run_dbt_staging          (dbt: Staging + Intermediate DuckDB)
    → sync_silver_layer        (Python: 3NF PostgreSQL + SCD Type 2 + CDC Watermark)
    → run_gold_dwh             (Python: Silver → DWH PostgreSQL Stored Procs)
    → export_gold_marts        (Python: DWH → Delta Lake Gold + Parquet fallback)
    → vacuum_delta_tables      (Maintenance: Delta VACUUM – xóa file cũ > 7 ngày)
  → end

Schedule: 6h sáng mỗi ngày (Asia/Ho_Chi_Minh)
"""
import json
import subprocess
import time
import os
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

    cmd = [
        "python",
        "/opt/airflow/scripts/run_scrapers.py",
        "--mode", "full",
        "--workers", "3",
        "--run-type", "auto",
    ]
    
    # Tự động loại trừ linkedin nếu chưa có session cookie
    if not os.path.exists("/opt/airflow/data/auth/linkedin_session.json") and \
       not os.path.exists("/opt/airflow/data/linkedin_session.json"):  # legacy fallback
        cmd.extend(["--exclude", "linkedin"])

    # Chạy lệnh bằng Popen để log được stream trực tiếp lên giao diện Airflow
    process = subprocess.Popen(
        cmd,
        cwd="/opt/airflow",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    stdout_lines = []
    # Stream logs live
    for line in process.stdout:
        print(line, end="")
        stdout_lines.append(line)

    try:
        returncode = process.wait(timeout=18000) # 5 tiếng timeout
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError("run_scrapers.py bị treo (hang) và quá thời gian chờ 5 tiếng.")

    duration = time.monotonic() - t0
    stdout = "".join(stdout_lines)

    # ----- Parse metrics từ stdout -----
    success_count = 0
    failed_count  = 0
    total_records = 0
    scraper_rows: list[dict] = []

    for line in stdout.splitlines():
        if " ok" in line or " fail" in line:
            parts = line.split()
            try:
                name    = next((p for p in parts if p.isalpha() and len(p) > 2), "")
                status  = "ok" if " ok" in line else "fail"
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
        "exit_code":      returncode,
        "scrapers":       scraper_rows,
    }

    ti.xcom_push(key="scraper_metrics", value=metrics)

    print("=" * 60)
    print("  SCRAPER METRICS")
    print("=" * 60)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print("=" * 60)

    if returncode != 0:
        raise RuntimeError(
            f"run_scrapers.py exited with code {returncode}. "
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
        execution_timeout=timedelta(hours=5, minutes=15),
        doc_md="Chạy toàn bộ scrapers song song và push metrics lên XCom",
    )

    # ── Task 2: dbt (Staging) ────────────────
    run_dbt_staging = BashOperator(
        task_id="run_dbt_staging",
        bash_command=(
            "dbt run "
            "--select staging intermediate "
            "--profiles-dir /opt/airflow/dbt_jobitvn "
            "--project-dir /opt/airflow/dbt_jobitvn"
        ),
        doc_md="Chạy dbt models cho tầng Staging và Intermediate (DuckDB).",
    )

    # ── Task 3: Sync Silver Layer ───────────────────────
    def _sync_silver_layer(**kwargs):
        """Khởi tạo SilverSyncEngine và JobDedupEngine để nạp vào DB 3NF.
        
        Cải tiến v2.0: Tích hợp CDCWatermarkTracker — ghi log run_id và cập nhật
        watermark sau khi sync thành công.
        """
        import sys
        import time
        from datetime import datetime
        sys.path.insert(0, "/opt/airflow")
        
        from src.silver.sync_engine import SilverSyncEngine
        from src.silver.dedup_engine import JobDedupEngine
        from src.silver.cdc_tracker import CDCWatermarkTracker
        
        session_id = int(time.time())
        session_start_time = datetime.utcnow().isoformat()
        
        tracker = CDCWatermarkTracker()
        tracker.connect()
        
        # 1. Sync Jobs vào PostgreSQL Silver
        sync_engine = SilverSyncEngine(duckdb_path="/opt/airflow/data/jobitvn.duckdb")
        sync_engine.connect()
        run_id = tracker.start_run(source_code=None, stage="silver")
        try:
            sync_engine.sync_staged_jobs(session_id=session_id)
            for src_id in range(1, 12):
                sync_engine.run_lifecycle_checks(
                    source_id=src_id,
                    session_id=session_id,
                    session_start_time=session_start_time
                )
            tracker.complete_run(run_id, status="SUCCESS")
        except Exception as e:
            tracker.fail_run(run_id, e)
            raise
        finally:
            sync_engine.close()
            
        # 2. Dedup cross-source
        dedup_engine = JobDedupEngine()
        dedup_engine.connect()
        dedup_run_id = tracker.start_run(source_code=None, stage="dedup")
        try:
            dedup_engine.run_dedup_pipeline(session_id=session_id)
            tracker.complete_run(dedup_run_id, status="SUCCESS")
        except Exception as e:
            tracker.fail_run(dedup_run_id, e)
            raise
        finally:
            dedup_engine.close()
            tracker.close()
            
        return {"session_id": session_id, "status": "success"}

    sync_silver_layer = PythonOperator(
        task_id="sync_silver_layer",
        python_callable=_sync_silver_layer,
        execution_timeout=timedelta(minutes=30),
        doc_md="Sync dữ liệu từ DuckDB Staging vào PostgreSQL Silver (chống N+1, cập nhật SCD, TF-IDF dedup).",
    )

    # ── Task 4: Run Gold DWH (DuckDB Native) ───────────────────────
    run_dbt_gold = BashOperator(
        task_id="run_dbt_gold",
        bash_command=(
            "dbt run --select marts "
            "--target duckdb_dev "
            "--profiles-dir /opt/airflow/dbt_jobitvn "
            "--project-dir /opt/airflow/dbt_jobitvn"
        ),
        doc_md="Build Gold DWH và Marts bằng DuckDB siêu tốc.",
    )

    # ── Task 4.5: Sync PostgreSQL Gold (Web API & Power BI) ────────
    def _sync_postgres_gold(**kwargs):
        """
        Khởi chạy các Stored Procedures để đồng bộ và cập nhật 
        Gold DWH & Materialized Views trên PostgreSQL phục vụ Web API và PowerBI.
        """
        import sys
        sys.path.insert(0, "/opt/airflow")
        import psycopg2
        from src.config import DBConfig
        
        conn = psycopg2.connect(DBConfig.dsn())
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                print("Syncing dimensions...")
                cur.execute("CALL dwh.sp_sync_dim_source();")
                cur.execute("CALL dwh.sp_sync_dim_company();")
                print("Syncing facts...")
                cur.execute("CALL dwh.sp_sync_fact_job_posting();")
                print("Syncing skills and locations...")
                cur.execute("CALL dwh.sp_sync_skills_and_locations();")
                print("Refreshing materialized views for Web API and Power BI...")
                cur.execute("CALL dwh.sp_refresh_mart_api();")
                cur.execute("CALL dwh.sp_refresh_all_materialized_views();")
                print("PostgreSQL Gold Sync completed successfully.")
        finally:
            conn.close()
            
        return {"status": "success"}

    sync_postgres_gold = PythonOperator(
        task_id="sync_postgres_gold",
        python_callable=_sync_postgres_gold,
        execution_timeout=timedelta(minutes=30),
        doc_md="Cập nhật Gold schema trên Postgres cho Web Portal và PowerBI.",
    )

    # ── Task 5: Vacuum Delta Tables ─────────────────────────────────────────
    def _vacuum_delta_tables(**kwargs):
        """
        Chạy VACUUM trên tất cả Delta Tables — xóa file cũ quá retention period.
        Giữ lại 7 ngày lịch sử (VACUUM_RETENTION_HOURS=168).
        
        Chạy cuối pipeline sau khi đã export xong — không ảnh hưởng pipeline chính.
        """
        import sys
        sys.path.insert(0, "/opt/airflow")
        from src.storage.delta_manager import DeltaLakeManager
        
        manager = DeltaLakeManager()
        
        # Vacuum tất cả Bronze sources
        bronze_sources = [
            "topcv", "itviec", "linkedin", "vietnamworks",
            "jobsgo", "123job", "careerviet", "joboko"
        ]
        bronze_results = manager.vacuum_all_bronze(bronze_sources)
        
        # Vacuum Gold marts
        gold_tables = [
            "mart_bi/agg_demand_trend",
            "mart_bi/agg_salary_by_company",
            "mart_bi/kpi_daily_summary",
            "mart_bi/agg_skill_trend_weekly",
            "mart_ml/job_features",
        ]
        gold_results = {}
        for tbl in gold_tables:
            gold_results[tbl] = manager.vacuum_table(tbl, layer="gold")
        
        return {"bronze": bronze_results, "gold": gold_results}

    vacuum_delta_tables = PythonOperator(
        task_id="vacuum_delta_tables",
        python_callable=_vacuum_delta_tables,
        execution_timeout=timedelta(minutes=15),
        trigger_rule="all_done",
        doc_md="VACUUM tất cả Delta Tables Bronze + Gold. Xóa file cũ > 7 ngày.",
    )

    # ── Task 6: Archive Bronze Data (v2.1) ──────────────────────────────────
    def _archive_bronze_data(**kwargs):
        """
        Gom nén dữ liệu JSON thô cũ hơn 30 ngày thành Parquet ZSTD
        để giải phóng dung lượng ổ cứng local.
        """
        import sys
        sys.path.insert(0, "/opt/airflow")
        from src.lifecycle.bronze_archiver import archive_old_bronze_partitions
        
        archive_old_bronze_partitions(days_to_keep=30)
        return {"status": "success"}

    archive_bronze_data = PythonOperator(
        task_id="archive_bronze_data",
        python_callable=_archive_bronze_data,
        execution_timeout=timedelta(minutes=20),
        trigger_rule="all_done",
        doc_md="Gom nén JSON thô Bronze cũ > 30 ngày thành Parquet ZSTD trên S3.",
    )

    end = EmptyOperator(task_id="end")

    # Workflow dependencies (DAG Graph)
    start >> crawl_all_sources >> run_dbt_staging
    
    # Phân nhánh song song (Tiết kiệm thời gian)
    run_dbt_staging >> sync_silver_layer >> sync_postgres_gold
    run_dbt_staging >> run_dbt_gold
    run_dbt_staging >> archive_bronze_data
    
    [sync_postgres_gold, run_dbt_gold] >> vacuum_delta_tables >> end
