import logging
import psycopg2
from psycopg2.extras import DictCursor, execute_values
import duckdb
import pandas as pd
from datetime import date
from typing import Optional

from src.config import DBConfig

logger = logging.getLogger(__name__)

def clean_str(val) -> Optional[str]:
    if pd.isna(val) or val is None:
        return None
    val_str = str(val).strip()
    if val_str.lower() in ("nan", "none", "null", ""):
        return None
    return val_str


class SilverSyncEngine:
    def __init__(self, duckdb_path: str = "jobitvn.duckdb"):
        self.duckdb_path = duckdb_path
        self.pg_conn = None
        self.duck_conn = None

    def connect(self):
        self.pg_conn = psycopg2.connect(DBConfig.dsn())
        self.pg_conn.autocommit = False # We manage transactions manually
        self.duck_conn = duckdb.connect(self.duckdb_path)
        logger.info("Connected to PostgreSQL and DuckDB.")

    def close(self):
        if self.pg_conn:
            self.pg_conn.close()
        if self.duck_conn:
            self.duck_conn.close()

    def sync_staged_jobs(self, session_id: int):
        """
        Đọc từ int_changed_jobs (bằng DuckDB), bulk insert vào staging.stg_jobs,
        và gọi SP xử lý hàng loạt sp_process_staging_batch.
        """
        logger.info("Starting batch sync from DuckDB staging to PostgreSQL Silver 3NF...")
        
        try:
            df = self.duck_conn.execute("SELECT * FROM int_changed_jobs").df()
        except duckdb.CatalogException:
            logger.warning("Table 'int_changed_jobs' not found in DuckDB. Did you run dbt?")
            return
            
        if df.empty:
            logger.info("No new/changed jobs to sync.")
            return

        logger.info(f"Found {len(df)} records in int_changed_jobs to sync. Preparing bulk insert...")

        # Chuẩn bị dữ liệu cho execute_values
        insert_query = """
            INSERT INTO staging.stg_jobs (
                source_code, source_job_id, canonical_url,
                title_raw, company_raw, location_raw, salary_raw, experience_raw,
                skills_raw, description, deadline_raw,
                title_clean, company_normalized, salary_min, salary_max,
                experience_min_years, experience_max_years,
                identity_hash, content_hash, scraped_at, batch_date
            ) VALUES %s
        """

        batch_date = date.today()
        records_to_insert = []
        for _, row in df.iterrows():
            if hasattr(row['skills_raw'], 'tolist') and row['skills_raw'] is not None:
                skills = row['skills_raw'].tolist()
            elif isinstance(row['skills_raw'], (list, tuple, pd.Series)):
                skills = list(row['skills_raw'])
            else:
                skills = None
            records_to_insert.append((
                clean_str(row['source_code']),
                clean_str(str(row['source_job_id'])),
                clean_str(row['canonical_url']),
                clean_str(row['title_raw']),
                clean_str(row['company_raw']),
                clean_str(row['location_raw']),
                clean_str(row['salary_raw']),
                clean_str(row['experience_raw']),
                skills,
                clean_str(row['description']),
                clean_str(row['deadline_raw']),
                clean_str(row['title_clean']),
                clean_str(row['company_normalized'] if 'company_normalized' in row else row['company_raw']),
                row['salary_min'] if not pd.isna(row['salary_min']) else None,
                row['salary_max'] if not pd.isna(row['salary_max']) else None,
                row['experience_min_years'] if not pd.isna(row['experience_min_years']) else None,
                row['experience_max_years'] if not pd.isna(row['experience_max_years']) else None,
                row['identity_hash'],
                row['content_hash'],
                row['scraped_at'],
                batch_date
            ))

        with self.pg_conn.cursor() as cur:
            try:
                # 1. Xóa dữ liệu staging cũ của ngày hôm nay để tránh duplicate data batch
                cur.execute("DELETE FROM staging.stg_jobs WHERE batch_date = %s", (batch_date,))
                
                # 2. Bulk Insert vào staging.stg_jobs
                logger.info(f"Executing bulk insert of {len(records_to_insert)} records to staging.stg_jobs...")
                execute_values(cur, insert_query, records_to_insert, page_size=1000)
                
                # 3. Create Crawl Session for the batch to satisfy FK constraints
                cur.execute("""
                    INSERT INTO silver.crawl_sessions (session_id, run_date, crawl_status)
                    VALUES (%s, %s, 'RUNNING')
                    ON CONFLICT DO NOTHING;
                """, (session_id, batch_date))
                
                # 4. Chạy DB-side Processing
                logger.info("Calling silver.sp_process_staging_batch() for Set-Based UPSERT...")
                cur.execute("CALL silver.sp_process_staging_batch(%s, %s)", (session_id, batch_date))
                
                # Commit transaction
                self.pg_conn.commit()
                logger.info("Batch sync complete successfully.")
                
            except Exception as e:
                self.pg_conn.rollback()
                logger.error(f"Error during batch sync: {e}")
                raise e

    def run_lifecycle_checks(self, source_id: int, session_id: int, session_start_time: str):
        """
        Gọi logic auto-close tin bị biến mất
        """
        with self.pg_conn.cursor() as cur:
            cur.execute("""
                SELECT silver.sp_auto_close_missing_jobs(%s::SMALLINT, %s::BIGINT, %s::TIMESTAMPTZ)
            """, (source_id, session_id, session_start_time))
            closed_count = cur.fetchone()[0]
            
            cur.execute("""
                SELECT silver.sp_auto_expire_deadline()
            """)
            expired_count = cur.fetchone()[0]
            self.pg_conn.commit()
            
        logger.info(f"Lifecycle checks run: {closed_count} jobs auto-closed, {expired_count} jobs auto-expired.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = SilverSyncEngine()
    engine.connect()
    try:
        # Đảm bảo có session_id = 1 trong database để tránh lỗi FK
        with engine.pg_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO silver.crawl_sessions (session_id, run_date, source_id, crawl_status)
                VALUES (1, CURRENT_DATE, 1, 'RUNNING')
                ON CONFLICT DO NOTHING;
            """)
            cur.execute("SELECT setval('silver.crawl_sessions_session_id_seq', COALESCE((SELECT MAX(session_id) FROM silver.crawl_sessions), 1))")
            engine.pg_conn.commit()

        # Mock session ID for standalone test
        engine.sync_staged_jobs(session_id=1)
    finally:
        engine.close()

