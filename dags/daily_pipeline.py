"""
daily_pipeline.py — Airflow DAG: pipeline hàng ngày cho toàn bộ job portals.

Flow: start → crawl_all_sources → run_dbt_models → end
Schedule: 6h sáng mỗi ngày (Asia/Ho_Chi_Minh)
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    "owner": "data-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

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

    crawl_all_sources = BashOperator(
        task_id="crawl_all_sources",
        bash_command="python /opt/airflow/scripts/run_scrapers.py --mode full --workers 4",
        execution_timeout=timedelta(minutes=60),
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
