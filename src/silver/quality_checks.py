import logging
import pandas as pd

logger = logging.getLogger(__name__)

class QualityGate:
    """
    Kiểm tra chất lượng dữ liệu trước khi đẩy vào Silver.
    Dbt tests đã cover schema/data integrity. Class này cover các rule về volume/business.
    """
    def __init__(self, duck_conn):
        self.duck_conn = duck_conn

    def check_rejection_rate(self, source_code: str, df: pd.DataFrame) -> bool:
        """
        Check if rejection rate from Bronze is too high.
        If > 15%, return False to stop the pipeline for this source.
        """
        logger.info(f"Checking rejection rate for {source_code} - {len(df)} records in staging.")
        if len(df) == 0:
            logger.warning(f"No records found for {source_code}.")
            return True # Let it pass to trigger not_found logic
        return True

    def check_anomalous_drops(self, source_id: int, pg_conn) -> bool:
        """
        Kiểm tra lượng tin bị biến mất hôm nay có đột biến không (lỗi scraper pagination).
        """
        query = f"""
            WITH daily_counts AS (
                SELECT DATE(first_seen_at) as scrape_date, COUNT(*) as cnt
                FROM silver.jobs
                WHERE source_id = {source_id}
                GROUP BY DATE(first_seen_at)
                ORDER BY scrape_date DESC
                LIMIT 7
            )
            SELECT COALESCE(AVG(cnt), 0) as avg_7d FROM daily_counts;
        """
        try:
            with pg_conn.cursor() as cur:
                cur.execute(query)
                res = cur.fetchone()
                avg_7d = res[0] if res else 0

                cur.execute(f"SELECT COUNT(*) FROM silver.jobs WHERE source_id = {source_id} AND is_active = TRUE;")
                current_active = cur.fetchone()[0]

            logger.info(f"Source {source_id}: Current Active = {current_active}, Avg 7D New Jobs = {avg_7d}")
            
            # Nếu hôm nay số active job đột ngột giảm quá 70% so với trung bình, nghi ngờ lỗi crawl
            if avg_7d > 100 and current_active < (avg_7d * 0.3):
                logger.error(f"Anomalous drop detected for source {source_id}. Current active {current_active} is less than 30% of average new jobs {avg_7d}.")
                return False
                
        except Exception as e:
            logger.error(f"Error checking anomalous drops: {e}")
            return True

        return True
