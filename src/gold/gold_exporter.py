import os
import logging
import pandas as pd
import duckdb
import psycopg2

from src.config import DBConfig, DATA_MART_BI_DIR, DATA_MART_ML_DIR
from src.storage.delta_manager import DeltaLakeManager

logger = logging.getLogger(__name__)

class GoldExporter:
    """
    Export dữ liệu từ PostgreSQL (DWH) ra 2 format song song:

    ┌──────────────────────────────────────────────────────────────┐
    │  1. Delta Lake  →  data/gold/mart_bi/<table>/          (primary)│
    │     • Hỗ trợ time-travel, ACID, DuckDB query trực tiếp   │
    │     • Được quản lý bởi DeltaLakeManager               │
    ├──────────────────────────────────────────────────────────────┤
    │  2. Parquet     →  data/mart_bi/<table>.parquet         (fallback)│
    │     • Cho Power BI Desktop, quick pandas read           │
    │     • Path được định nghĩa trong src/config.py           │
    └──────────────────────────────────────────────────────────────┘
    """
    def __init__(self, output_dir: str | None = None):
        # Parquet fallback dirs — lay từ config (data/mart_bi, data/mart_ml)
        self.mart_bi_dir = str(DATA_MART_BI_DIR)
        self.mart_ml_dir = str(DATA_MART_ML_DIR)
        self.pg_conn = None
        self.duck_conn = None
        self.delta_manager = DeltaLakeManager()

        # Khởi tạo thư mục Parquet fallback nếu chưa tồn tại
        DATA_MART_BI_DIR.mkdir(parents=True, exist_ok=True)
        DATA_MART_ML_DIR.mkdir(parents=True, exist_ok=True)

    def connect(self):
        self.pg_conn = psycopg2.connect(DBConfig.dsn())
        self.duck_conn = duckdb.connect(':memory:')
        logger.info("Connected to PostgreSQL and DuckDB for Gold Export.")

    def close(self):
        if self.pg_conn:
            self.pg_conn.close()
        if self.duck_conn:
            self.duck_conn.close()

    def run_dwh_sync(self):
        """
        Gọi các Stored Procedures để đồng bộ Silver -> DWH trong Postgres.
        """
        logger.info("Syncing Silver -> Gold DWH...")
        with self.pg_conn.cursor() as cur:
            cur.execute("CALL dwh.sp_sync_dim_source();")
            cur.execute("CALL dwh.sp_sync_dim_company();")
            cur.execute("CALL dwh.sp_sync_fact_job_posting();")
            cur.execute("CALL dwh.sp_sync_skills_and_locations();")
            cur.execute("CALL dwh.sp_refresh_mart_api();")
            self.pg_conn.commit()
        logger.info("Silver -> Gold DWH sync complete.")

    def export_mart_bi(self):
        """
        Export Data Mart cho BI ra Delta Lake (Gold tier).
        Delta format cho phép Power BI / DuckDB Time Travel trực tiếp.
        Local Parquet được ghi song song làm fallback cho Power BI Desktop.
        """
        logger.info("Exporting mart_bi to Delta Lake (Gold)...")

        # 1. agg_demand_trend
        query_demand = """
            SELECT
                d.year,
                d.month,
                c.industry,
                COUNT(f.job_posting_fact_id) AS total_jobs
            FROM dwh.fct_job_posting f
            JOIN dwh.dim_date d ON f.posted_date_key = d.date_key
            JOIN dwh.dim_company c ON f.company_key = c.company_key
            WHERE f.is_active = TRUE
            GROUP BY 1, 2, 3
        """
        df_demand = pd.read_sql(query_demand, self.pg_conn)
        # Ghi Delta (primary)
        self.delta_manager.write_gold_mart("mart_bi", "agg_demand_trend", df_demand)
        # Ghi Parquet local (fallback cho Power BI Desktop)
        out_demand = os.path.join(self.mart_bi_dir, "agg_demand_trend.parquet")
        self.duck_conn.execute(f"COPY (SELECT * FROM df_demand) TO '{out_demand}' (FORMAT PARQUET)")

        # 2. agg_salary_by_company
        query_salary = """
            SELECT
                c.company_name,
                c.industry,
                AVG(f.salary_midpoint_vnd) AS avg_salary,
                MIN(f.salary_min_vnd) AS min_salary,
                MAX(f.salary_max_vnd) AS max_salary
            FROM dwh.fct_job_posting f
            JOIN dwh.dim_company c ON f.company_key = c.company_key
            WHERE f.has_salary = TRUE
            GROUP BY 1, 2
        """
        df_salary = pd.read_sql(query_salary, self.pg_conn)
        self.delta_manager.write_gold_mart("mart_bi", "agg_salary_by_company", df_salary)
        out_salary = os.path.join(self.mart_bi_dir, "agg_salary_by_company.parquet")
        self.duck_conn.execute(f"COPY (SELECT * FROM df_salary) TO '{out_salary}' (FORMAT PARQUET)")

        logger.info("mart_bi export complete (Delta + Parquet).")

    def export_mart_ml(self):
        """
        Export Data Mart cho ML ra Delta Lake (Gold tier).
        Flat table với label rõ ràng cho Salary Prediction / Job Recommendation.
        """
        logger.info("Exporting mart_ml to Delta Lake (Gold)...")

        # 1. job_features (Features for prediction/recommendation)
        query_ml = """
            SELECT
                f.job_posting_fact_id AS job_id,
                c.industry,
                c.company_size_category,
                f.experience_min_years,
                f.is_intern,
                f.is_fresher,
                f.salary_midpoint_vnd AS label_salary
            FROM dwh.fct_job_posting f
            JOIN dwh.dim_company c ON f.company_key = c.company_key
            WHERE f.is_active = TRUE
        """
        df_ml = pd.read_sql(query_ml, self.pg_conn)
        self.delta_manager.write_gold_mart("mart_ml", "job_features", df_ml)
        # Parquet fallback
        out_ml = os.path.join(self.mart_ml_dir, "job_features.parquet")
        self.duck_conn.execute(f"COPY (SELECT * FROM df_ml) TO '{out_ml}' (FORMAT PARQUET)")

        logger.info("mart_ml export complete (Delta + Parquet).")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import warnings
    warnings.simplefilter(action='ignore', category=UserWarning) # Bỏ qua warning pandas psycopg2
    
    exporter = GoldExporter()
    exporter.connect()
    try:
        exporter.run_dwh_sync()
        exporter.export_mart_bi()
        exporter.export_mart_ml()
    finally:
        exporter.close()
