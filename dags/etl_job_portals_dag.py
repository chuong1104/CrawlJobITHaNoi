from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    'owner': 'data-platform',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'daily_job_pipeline',
    default_args=default_args,
    description='Daily ETL pipeline for job portals (Extract -> Transform -> Load)',
    schedule_interval='0 6 * * *', # Chạy lúc 6h sáng mỗi ngày
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['jobitvn', 'elt'],
) as dag:

    start = EmptyOperator(task_id='start')

    # Bước 1: Gọi script cào dữ liệu song song
    crawl_sources = BashOperator(
        task_id='crawl_all_sources',
        bash_command='python /opt/airflow/run_scrapers_once.py --mode full --workers 4',
        execution_timeout=timedelta(minutes=60),
    )

    # Bước 2: Chạy dbt để biến đổi dữ liệu (Transform)
    # Hiện tại để dạng echo. Khi bạn mount thư mục dbt_jobitvn vào docker-compose, có thể đổi thành lệnh dbt thật
    run_dbt_models = BashOperator(
        task_id='run_dbt_models',
        bash_command='echo "Giả lập chạy: dbt run --profiles-dir /opt/airflow/dbt --project-dir /opt/airflow/dbt_jobitvn"',
    )

    end = EmptyOperator(task_id='end')

    # Định nghĩa luồng chạy
    start >> crawl_sources >> run_dbt_models >> end
