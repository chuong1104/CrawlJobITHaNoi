"""
cdc_tracker.py — CDC Watermark Tracker cho delta-load thông minh.

Thay thế cơ chế "full batch hàng ngày" bằng "watermark-based delta load":
  - Mỗi lần sync, chỉ xử lý records MỚI HƠN watermark timestamp gần nhất
  - Giảm 80-90% lượng dữ liệu cần xử lý trong dbt
  - Tự động phát hiện anomaly khi scraper bị block (ít records hơn kỳ vọng)
  - Ghi log chi tiết mỗi lần chạy vào silver.pipeline_run_log

Usage trong Airflow DAG:
    tracker = CDCWatermarkTracker()
    tracker.connect()
    
    watermark = tracker.get_watermark('topcv')
    # ... chạy scraper, lấy records mới hơn watermark ...
    run_id = tracker.start_run('topcv', 'bronze', watermark)
    # ... xử lý ...
    tracker.complete_run(run_id, records_new=120, records_updated=30)
    tracker.set_watermark('topcv', new_records=150)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import DictCursor

from src.config import DBConfig

logger = logging.getLogger("silver.cdc_tracker")


class CDCWatermarkTracker:
    """
    Theo dõi watermark timestamp cho mỗi source để thực hiện delta-load.
    
    Anomaly detection:
        - Nếu actual_count < expected_min * 0.5 trong 1 lần → anomaly_flag = TRUE
        - Nếu consecutive_low_runs >= 3 → critical alert (scraper có thể bị block)
    """

    ANOMALY_THRESHOLD_RATIO = 0.5   # < 50% expected → anomaly
    CRITICAL_CONSECUTIVE    = 3     # 3 lần liên tiếp thấp → critical

    def __init__(self):
        self.pg_conn = None

    def connect(self):
        self.pg_conn = psycopg2.connect(DBConfig.dsn())
        self.pg_conn.autocommit = False
        logger.info("CDCWatermarkTracker connected to PostgreSQL.")

    def close(self):
        if self.pg_conn:
            self.pg_conn.close()

    # ------------------------------------------------------------------
    # Watermark Operations
    # ------------------------------------------------------------------
    def get_watermark(self, source_code: str) -> datetime:
        """
        Trả về watermark timestamp của source. 
        Dữ liệu scrape CÓ scraped_at > watermark mới được xử lý.
        
        Returns:
            datetime với timezone UTC. 
            Epoch (1970-01-01) nếu chưa có watermark (lần đầu chạy → load full).
        """
        with self.pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                "SELECT last_sync_at FROM silver.cdc_watermarks WHERE source_code = %s",
                (source_code,)
            )
            row = cur.fetchone()

        if row:
            ts = row["last_sync_at"]
            logger.info(f"[{source_code}] Watermark: {ts.isoformat()}")
            return ts
        else:
            # Source chưa có watermark → full load
            logger.warning(
                f"[{source_code}] No watermark found — will perform full load. "
                f"Run 02_create_cdc_tables.sql to initialize."
            )
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    def set_watermark(
        self,
        source_code: str,
        new_records: int,
        batch_date: Optional[str] = None,
        watermark_ts: Optional[datetime] = None,
    ) -> None:
        """
        Cập nhật watermark sau khi sync thành công.
        Tự động detect anomaly nếu new_records thấp hơn kỳ vọng.
        
        Args:
            source_code:  Tên nguồn
            new_records:  Số records đã xử lý trong lần này
            batch_date:   Ngày batch (YYYY-MM-DD), mặc định hôm nay
            watermark_ts: Timestamp watermark mới, mặc định NOW()
        """
        now = watermark_ts or datetime.now(timezone.utc)
        batch_date = batch_date or now.strftime("%Y-%m-%d")

        with self.pg_conn.cursor(cursor_factory=DictCursor) as cur:
            # Lấy thông tin hiện tại để tính anomaly
            cur.execute(
                """
                SELECT expected_min_count, consecutive_low_runs 
                FROM silver.cdc_watermarks 
                WHERE source_code = %s
                """,
                (source_code,)
            )
            row = cur.fetchone()
            expected = row["expected_min_count"] if row else 50
            consecutive = row["consecutive_low_runs"] if row else 0

            # Anomaly detection
            is_anomaly = new_records < int(expected * self.ANOMALY_THRESHOLD_RATIO)
            new_consecutive = (consecutive + 1) if is_anomaly else 0
            anomaly_reason = None

            if is_anomaly:
                anomaly_reason = (
                    f"Got {new_records} records, expected >= {int(expected * self.ANOMALY_THRESHOLD_RATIO)}. "
                    f"Consecutive low runs: {new_consecutive}."
                )
                level = "CRITICAL" if new_consecutive >= self.CRITICAL_CONSECUTIVE else "WARNING"
                logger.warning(f"[{source_code}]  {level} ANOMALY: {anomaly_reason}")
            else:
                logger.info(f"[{source_code}]  Watermark updated: {now.isoformat()} ({new_records} records)")

            # UPSERT watermark
            cur.execute(
                """
                INSERT INTO silver.cdc_watermarks (
                    source_code, last_sync_at, last_batch_date, last_job_count,
                    anomaly_flag, anomaly_reason, consecutive_low_runs
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_code) DO UPDATE SET
                    last_sync_at         = EXCLUDED.last_sync_at,
                    last_batch_date      = EXCLUDED.last_batch_date,
                    last_job_count       = EXCLUDED.last_job_count,
                    anomaly_flag         = EXCLUDED.anomaly_flag,
                    anomaly_reason       = EXCLUDED.anomaly_reason,
                    consecutive_low_runs = EXCLUDED.consecutive_low_runs,
                    updated_at           = NOW()
                """,
                (
                    source_code, now, batch_date, new_records,
                    is_anomaly, anomaly_reason, new_consecutive,
                )
            )
            self.pg_conn.commit()

    def get_all_watermarks(self) -> dict[str, datetime]:
        """Trả về dict {source_code: watermark_ts} cho tất cả sources."""
        with self.pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT source_code, last_sync_at FROM silver.cdc_watermarks")
            return {row["source_code"]: row["last_sync_at"] for row in cur.fetchall()}

    def get_anomaly_sources(self) -> list[dict]:
        """Trả về danh sách sources đang có anomaly flag = TRUE."""
        with self.pg_conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                """
                SELECT source_code, last_sync_at, last_job_count, 
                       consecutive_low_runs, anomaly_reason
                FROM silver.cdc_watermarks
                WHERE anomaly_flag = TRUE
                ORDER BY consecutive_low_runs DESC
                """
            )
            return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Pipeline Run Logging
    # ------------------------------------------------------------------
    def start_run(
        self,
        source_code: Optional[str],
        stage: str,
        watermark_from: Optional[datetime] = None,
        pipeline_name: str = "daily_job_pipeline",
    ) -> int:
        """
        Ghi log bắt đầu một pipeline run. Trả về run_id.
        
        Args:
            source_code:   Tên source (None nếu stage không specific-source)
            stage:         'bronze', 'silver', 'gold', 'dbt', 'vacuum'
            watermark_from: Timestamp watermark bắt đầu
            pipeline_name: Tên pipeline
            
        Returns:
            run_id để dùng khi gọi complete_run()
        """
        with self.pg_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO silver.pipeline_run_log 
                    (pipeline_name, source_code, stage, watermark_from, status)
                VALUES (%s, %s, %s, %s, 'RUNNING')
                RETURNING run_id
                """,
                (pipeline_name, source_code, stage, watermark_from)
            )
            run_id = cur.fetchone()[0]
            self.pg_conn.commit()
        logger.info(f"[{stage}] Pipeline run started: run_id={run_id}")
        return run_id

    def complete_run(
        self,
        run_id: int,
        records_extracted: int = 0,
        records_new: int = 0,
        records_updated: int = 0,
        records_unchanged: int = 0,
        records_rejected: int = 0,
        watermark_to: Optional[datetime] = None,
        status: str = "SUCCESS",
        error_message: Optional[str] = None,
    ) -> None:
        """Đánh dấu pipeline run hoàn thành và cập nhật metrics."""
        watermark_to = watermark_to or datetime.now(timezone.utc)
        with self.pg_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE silver.pipeline_run_log SET
                    records_extracted  = %s,
                    records_new        = %s,
                    records_updated    = %s,
                    records_unchanged  = %s,
                    records_rejected   = %s,
                    watermark_to       = %s,
                    status             = %s,
                    error_message      = %s,
                    completed_at       = NOW()
                WHERE run_id = %s
                """,
                (
                    records_extracted, records_new, records_updated,
                    records_unchanged, records_rejected, watermark_to,
                    status, error_message, run_id,
                )
            )
            self.pg_conn.commit()
        logger.info(f"Pipeline run_id={run_id} completed: status={status}, new={records_new}, updated={records_updated}")

    def fail_run(self, run_id: int, error: Exception) -> None:
        """Đánh dấu pipeline run thất bại với thông tin lỗi."""
        self.complete_run(run_id, status="FAILED", error_message=str(error))
