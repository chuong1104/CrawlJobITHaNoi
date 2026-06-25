import logging
import psycopg2
from psycopg2.extras import DictCursor
import duckdb

from src.config import DBConfig

logger = logging.getLogger(__name__)

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
            
    def _get_source_id(self, cursor, source_code: str) -> int:
        cursor.execute("SELECT source_id FROM silver.sources WHERE source_code = %s", (source_code,))
        res = cursor.fetchone()
        if res:
            return res[0]
        # Insert if not exists (fallback)
        cursor.execute("INSERT INTO silver.sources (source_code, display_name, base_url) VALUES (%s, %s, %s) RETURNING source_id", (source_code, source_code, ''))
        return cursor.fetchone()[0]

    def _resolve_company(self, cursor, company_raw: str, source_id: int) -> int:
        cursor.execute("SELECT silver.sp_resolve_company(%s, %s)", (company_raw, source_id))
        return cursor.fetchone()[0]

    def sync_staged_jobs(self, session_id: int):
        """
        Đọc từ int_changed_jobs (bằng DuckDB) và gọi sp_upsert_job cho từng record (vào Postgres).
        Trong production, DuckDB có thể export ra Parquet và Bulk COPY, nhưng với upsert logic phức tạp,
        dùng executemany() hoặc loop là phù hợp hơn.
        """
        logger.info("Starting sync from DuckDB staging to PostgreSQL Silver 3NF...")
        
        # 1. Đọc dữ liệu từ dbt model int_changed_jobs bằng DuckDB
        # Giả định dbt đã run và tạo bảng/view này trong DuckDB
        try:
            df = self.duck_conn.execute("SELECT * FROM int_changed_jobs").df()
        except duckdb.CatalogException:
            logger.warning("Table 'int_changed_jobs' not found in DuckDB. Did you run dbt?")
            return
            
        if df.empty:
            logger.info("No new/changed jobs to sync.")
            return

        logger.info(f"Found {len(df)} records in int_changed_jobs to sync.")

        stats = {'NEW': 0, 'UPDATED': 0, 'UNCHANGED': 0, 'REOPENED': 0}

        with self.pg_conn.cursor() as cur:
            for index, row in df.iterrows():
                try:
                    # 2. Map source_id & company_id
                    source_id = self._get_source_id(cur, row['source_code'])
                    company_id = self._resolve_company(cur, row['company_raw'], source_id)

                    # 3. Call SP Upsert
                    cur.execute("""
                        SELECT silver.sp_upsert_job(
                            p_source_id := %s,
                            p_company_id := %s,
                            p_source_job_id := %s,
                            p_canonical_url := %s,
                            p_identity_hash := %s,
                            p_content_hash := %s,
                            p_title_raw := %s,
                            p_title_clean := %s,
                            p_description := %s,
                            p_salary_raw := %s,
                            p_salary_min := %s,
                            p_salary_max := %s,
                            p_experience_raw := %s,
                            p_experience_min := %s,
                            p_experience_max := %s,
                            p_job_level := 'UNKNOWN'::silver.job_level_enum,
                            p_job_type := 'UNKNOWN'::silver.job_type_enum,
                            p_work_mode := 'UNKNOWN'::silver.work_mode_enum,
                            p_job_family := NULL,
                            p_deadline_raw := %s,
                            p_deadline_date := NULL,
                            p_is_intern := FALSE,
                            p_is_fresher := FALSE,
                            p_scraped_at := %s,
                            p_session_id := %s
                        )
                    """, (
                        source_id,
                        company_id,
                        str(row['source_job_id']),
                        row['canonical_url'],
                        row['identity_hash'],
                        row['content_hash'],
                        row['title_raw'],
                        row['title_clean'],
                        row['description'],
                        row['salary_raw'],
                        row['salary_min'] if not pd.isna(row['salary_min']) else None,
                        row['salary_max'] if not pd.isna(row['salary_max']) else None,
                        row['experience_raw'],
                        row['experience_min_years'] if not pd.isna(row['experience_min_years']) else None,
                        row['experience_max_years'] if not pd.isna(row['experience_max_years']) else None,
                        row['deadline_raw'],
                        row['scraped_at'],
                        session_id
                    ))
                    
                    action_taken = cur.fetchone()[0]
                    stats[action_taken] = stats.get(action_taken, 0) + 1
                    
                except Exception as e:
                    self.pg_conn.rollback()
                    logger.error(f"Error syncing job {row['source_job_id']}: {e}")
                    raise e
            
            # Commit transaction for this batch
            self.pg_conn.commit()
            
        logger.info(f"Sync complete. Stats: {stats}")

    def run_lifecycle_checks(self, source_id: int, session_id: int, session_start_time: str):
        """
        Gọi logic auto-close tin bị biến mất
        """
        with self.pg_conn.cursor() as cur:
            cur.execute("""
                SELECT silver.sp_auto_close_missing_jobs(%s, %s, %s)
            """, (source_id, session_id, session_start_time))
            closed_count = cur.fetchone()[0]
            
            cur.execute("""
                SELECT silver.sp_auto_expire_deadline()
            """)
            expired_count = cur.fetchone()[0]
            self.pg_conn.commit()
            
        logger.info(f"Lifecycle checks run: {closed_count} jobs auto-closed, {expired_count} jobs auto-expired.")

if __name__ == "__main__":
    import pandas as pd # Ensure pandas is available for DuckDB
    logging.basicConfig(level=logging.INFO)
    engine = SilverSyncEngine()
    engine.connect()
    try:
        # Mock session ID for standalone test
        engine.sync_staged_jobs(session_id=1)
    finally:
        engine.close()
