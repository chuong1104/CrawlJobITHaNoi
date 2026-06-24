"""
daily_pipeline.py — Airflow DAG: pipeline hàng ngày cho toàn bộ job portals.

Flow: start → crawl_all_sources → run_dbt_models → end
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
# Task: crawl_all_sources — chạy scraper và đẩy metrics lên XCom
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
        # Dòng summary từ _print_scraper_done (detect ✔ / ✖)
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

    # Push metrics lên XCom để các task sau đọc được
    ti.xcom_push(key="scraper_metrics", value=metrics)

    # Log metrics vào Airflow task log
    print("=" * 60)
    print("  SCRAPER METRICS")
    print("=" * 60)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print("=" * 60)

    if stderr:
        print("\n--- STDERR (errors only) ---")
        # Chỉ in các dòng ERROR để không spam Airflow log
        for ln in stderr.splitlines():
            if any(k in ln.upper() for k in ("ERROR", "CRITICAL", "EXCEPTION", "TRACEBACK")):
                print(ln)

    # Fail task nếu scraper trả về exit code khác 0
    if result.returncode != 0:
        raise RuntimeError(
            f"run_scrapers.py exited with code {result.returncode}. "
            f"failed_count={failed_count}"
        )

    return metrics


with DAG(
    "daily_job_pipeline",
    default_args=default_args,
    description="Daily pipeline: Extract job postings → Bronze → dbt Transform",
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["jobitvn", "elt", "bronze"],
) as dag:

    start = EmptyOperator(task_id="start")

    crawl_all_sources = PythonOperator(
        task_id="crawl_all_sources",
        python_callable=_crawl_and_push_metrics,
        execution_timeout=timedelta(minutes=70),
        doc_md="""
## crawl_all_sources
Chạy toàn bộ scrapers song song và push metrics lên XCom:
- `scraper_metrics.success_count`
- `scraper_metrics.failed_count`
- `scraper_metrics.total_records`
- `scraper_metrics.duration_secs`
- `scraper_metrics.scrapers[]` — kết quả từng scraper
        """,
    )

    run_dbt_models = BashOperator(
        task_id="run_dbt_models",
        bash_command=(
            "dbt run "
            "--profiles-dir /opt/airflow/dbt "
            "--project-dir /opt/airflow/dbt_jobitvn"
        ),
    )

    end = EmptyOperator(task_id="end")

    start >> crawl_all_sources >> run_dbt_models >> end
