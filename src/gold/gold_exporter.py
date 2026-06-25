import os
import logging
import pandas as pd
import duckdb
import psycopg2

from src.config import DBConfig

logger = logging.getLogger(__name__)

class GoldExporter:
    """
    Class chịu trách nhiệm xuất dữ liệu từ PostgreSQL (DWH) ra file Parquet (Data Marts)
    phục vụ cho Power BI (mart_bi) và Machine Learning (mart_ml) thông qua DuckDB.
    """
    def __init__(self, output_dir: str = "data"):
        self.output_dir = output_dir
        self.mart_bi_dir = os.path.join(output_dir, "mart_bi")
        self.mart_ml_dir = os.path.join(output_dir, "mart_ml")
        self.pg_conn = None
        self.duck_conn = None
        
        # Đảm bảo thư mục tồn tại
        os.makedirs(self.mart_bi_dir, exist_ok=True)
        os.makedirs(self.mart_ml_dir, exist_ok=True)

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
            cur.execute("CALL dwh.sp_refresh_mart_api();")
            self.pg_conn.commit()
        logger.info("Silver -> Gold DWH sync complete.")

    def export_mart_bi(self):
        """
        Export Data Mart cho BI ra Parquet.
        Sử dụng Pandas đọc từ Postgres rồi dùng DuckDB chuyển sang Parquet Columnar.
        """
        logger.info("Exporting mart_bi to Parquet...")
        
        # 1. agg_demand_trend.parquet (Theo tháng, công ty, nguồn)
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
        out_demand = os.path.join(self.mart_bi_dir, "agg_demand_trend.parquet")
        self.duck_conn.execute(f"COPY (SELECT * FROM df_demand) TO '{out_demand}' (FORMAT PARQUET)")

        # 2. agg_salary_by_company.parquet
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
        out_salary = os.path.join(self.mart_bi_dir, "agg_salary_by_company.parquet")
        self.duck_conn.execute(f"COPY (SELECT * FROM df_salary) TO '{out_salary}' (FORMAT PARQUET)")
        
        logger.info("mart_bi export complete.")

    def export_mart_ml(self):
        """
        Export Data Mart cho ML ra Parquet.
        Tập trung vào Feature Engineering (Flat table với Label rõ ràng).
        """
        logger.info("Exporting mart_ml to Parquet...")
        
        # 1. job_features.parquet (Features list for prediction/recommendation)
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
        out_ml = os.path.join(self.mart_ml_dir, "job_features.parquet")
        self.duck_conn.execute(f"COPY (SELECT * FROM df_ml) TO '{out_ml}' (FORMAT PARQUET)")
        
        logger.info("mart_ml export complete.")

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
