import logging

logger = logging.getLogger(__name__)

class LifecycleManager:
    """
    Quản lý vòng đời tin tuyển dụng bổ sung nếu có logic không thể thực hiện bằng SQL.
    Đa phần logic vòng đời đã được đẩy xuống Stored Procedures (sp_upsert_job, sp_auto_close_missing_jobs).
    Class này có thể dùng để orchestrate các task lifecycle đặc biệt (vd: alert).
    """
    def __init__(self, pg_conn):
        self.pg_conn = pg_conn

    def process_manual_review_queue(self):
        # Placeholder cho các job bị cờ INVALID cần review tay
        pass
