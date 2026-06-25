import logging

logger = logging.getLogger(__name__)

class QualityGate:
    """
    Kiểm tra chất lượng dữ liệu trước khi đẩy vào Silver.
    Dbt tests đã cover schema/data integrity. Class này cover các rule về volume/business.
    """
    def __init__(self, duck_conn):
        self.duck_conn = duck_conn

    def check_rejection_rate(self, source_code: str, df) -> bool:
        """
        Check if rejection rate from Bronze is too high.
        If > 15%, return False to stop the pipeline for this source.
        """
        # Logic here...
        return True

    def check_anomalous_drops(self, source_id: int, pg_conn) -> bool:
        """
        Kiểm tra lượng tin bị biến mất hôm nay có đột biến không (lỗi scraper pagination).
        """
        # Logic here...
        return True
