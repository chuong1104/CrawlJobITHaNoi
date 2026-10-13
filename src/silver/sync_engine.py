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
    if "\x00" in val_str:
        val_str = val_str.replace("\x00", "")
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
        self._ensure_schema_compatibility()

    def _ensure_schema_compatibility(self):
        """
        Đảm bảo các trường chuỗi có thể chứa dữ liệu dài (URL, Title, Company, ...)
        được chuyển sang TEXT, tránh lỗi:
        'psycopg2.errors.StringDataRightTruncation: value too long for type character varying(255)'

        Mỗi cột được ALTER độc lập trong transaction riêng để tránh việc lỗi phụ thuộc View/Materialized View
        ở một bảng (ví dụ silver.jobs) làm rollback các bảng khác (đặc biệt là bảng đệm staging.stg_jobs).
        """
        # 1. Bảng đệm staging.stg_jobs: Bắt buộc toàn bộ cột chuỗi thô và đã chuẩn hóa phải là TEXT
        stg_columns = [
            "canonical_url", "title_raw", "title_clean", "company_raw",
            "company_normalized", "location_raw", "location_normalized",
            "salary_raw", "experience_raw", "deadline_raw", "description",
            "source_job_id", "job_type_raw", "job_family"
        ]

        # Lấy thêm động các cột character varying hiện có trong staging.stg_jobs (nếu có)
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = 'staging' 
                      AND table_name = 'stg_jobs' 
                      AND data_type = 'character varying'
                      AND column_name NOT IN ('source_code', 'salary_currency', 'pipeline_version', 'change_type');
                """)
                dynamic_cols = [r[0] for r in cur.fetchall()]
                for c in dynamic_cols:
                    if c not in stg_columns:
                        stg_columns.append(c)
            self.pg_conn.commit()
        except Exception as e:
            self.pg_conn.rollback()
            logger.debug(f"Could not query dynamic varchar columns in staging.stg_jobs: {e}")

        for col in stg_columns:
            try:
                with self.pg_conn.cursor() as cur:
                    cur.execute(f"ALTER TABLE staging.stg_jobs ALTER COLUMN {col} TYPE TEXT;")
                self.pg_conn.commit()
                logger.info(f"Verified column staging.stg_jobs.{col} as TEXT.")
            except Exception as e:
                self.pg_conn.rollback()
                logger.debug(f"Note: staging.stg_jobs.{col} alter skipped or already TEXT: {e}")

        # 2. Tầng Silver: Thử nâng cấp các cột bảng silver sang TEXT (từng cột độc lập)
        silver_targets = [
            ("silver.companies", ["normalized_name", "display_name", "website"]),
            ("silver.company_aliases", ["alias_text"]),
            ("silver.jobs", ["source_job_id", "canonical_url"]),
            ("silver.job_snapshots", [
                "title_raw", "title_clean", "salary_raw", "experience_raw",
                "deadline_raw", "description", "requirements"
            ]),
        ]
        for tbl, cols in silver_targets:
            for col in cols:
                try:
                    with self.pg_conn.cursor() as cur:
                        cur.execute(f"ALTER TABLE {tbl} ALTER COLUMN {col} TYPE TEXT;")
                    self.pg_conn.commit()
                except Exception as e:
                    self.pg_conn.rollback()
                    # Nếu cột đang được Materialized View tham chiếu, Postgres sẽ báo lỗi và bị bỏ qua an toàn
                    logger.debug(f"Skipping {tbl}.{col} (already TEXT or used by view): {e}")

        logger.info("Schema compatibility verified (VARCHAR columns widened to TEXT).")

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
        skipped_count = 0
        for _, row in df.iterrows():
            title_r = clean_str(row.get('title_raw'))
            company_r = clean_str(row.get('company_raw'))
            id_hash = clean_str(row.get('identity_hash'))
            c_hash = clean_str(row.get('content_hash'))

            # Bắt buộc phải có title_raw, company_raw và các hash để thỏa mãn ràng buộc NOT NULL của DB
            if not title_r or not company_r or not id_hash or not c_hash:
                skipped_count += 1
                continue

            if len(id_hash) > 16:
                id_hash = id_hash[:16]
            if len(c_hash) > 16:
                c_hash = c_hash[:16]

            if hasattr(row.get('skills_raw'), 'tolist') and row.get('skills_raw') is not None:
                skills = row['skills_raw'].tolist()
            elif isinstance(row.get('skills_raw'), (list, tuple, pd.Series)):
                skills = list(row['skills_raw'])
            else:
                skills = None

            source_c = clean_str(row.get('source_code'))
            if source_c and len(source_c) > 50:
                source_c = source_c[:50]

            sal_min = row['salary_min'] if not pd.isna(row.get('salary_min')) else None
            sal_max = row['salary_max'] if not pd.isna(row.get('salary_max')) else None
            if sal_min is not None and sal_max is not None and sal_min > sal_max:
                logger.warning(
                    f"Inconsistent salary range (min={sal_min} > max={sal_max}) for job {clean_str(row.get('source_job_id'))}. "
                    "Swapping to satisfy constraint."
                )
                sal_min, sal_max = sal_max, sal_min

            exp_raw = clean_str(row.get('experience_raw'))
            exp_min = int(row['experience_min_years']) if not pd.isna(row.get('experience_min_years')) else None
            exp_max = int(row['experience_max_years']) if not pd.isna(row.get('experience_max_years')) else None
            if exp_min is not None and exp_max is not None and exp_min > exp_max:
                if exp_raw and any(d in exp_raw for d in ['0.5', '0,5']):
                    exp_min, exp_max = 0, exp_max
                else:
                    exp_min, exp_max = min(exp_min, exp_max), max(exp_min, exp_max)
                logger.warning(
                    f"Adjusted inconsistent experience range for job {clean_str(row.get('source_job_id'))} "
                    f"(raw='{exp_raw}'): set min={exp_min}, max={exp_max} to satisfy chk_snapshot_exp constraint."
                )

            records_to_insert.append((
                source_c,
                clean_str(row.get('source_job_id')),
                clean_str(row.get('canonical_url')),
                title_r,
                company_r,
                clean_str(row.get('location_raw')),
                clean_str(row.get('salary_raw')),
                exp_raw,
                skills,
                clean_str(row.get('description')),
                clean_str(row.get('deadline_raw')),
                clean_str(row.get('title_clean')) or title_r,
                clean_str(row.get('company_normalized') if 'company_normalized' in row else company_r),
                sal_min,
                sal_max,
                exp_min,
                exp_max,
                id_hash,
                c_hash,
                row.get('scraped_at'),
                batch_date
            ))

        if skipped_count > 0:
            logger.warning(f"Skipped {skipped_count} invalid records missing title_raw, company_raw or hash keys.")

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

