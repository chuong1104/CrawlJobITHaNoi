"""
init_buckets.py — Khởi tạo S3/Floci buckets cho Lakehouse.

Chạy một lần khi setup môi trường:
    python -m src.storage.init_buckets
"""
import logging
from src.storage.s3_client import S3ClientWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("storage.init_buckets")

BUCKETS = ["jobit-bronze", "jobit-silver", "jobit-gold"]


def init_buckets(max_retries: int = 15, delay: float = 2.0) -> bool:
    import time
    logger.info("Initializing Lakehouse S3 Buckets on Floci...")
    for attempt in range(1, max_retries + 1):
        try:
            s3 = S3ClientWrapper()
            all_ok = True
            for bucket in BUCKETS:
                success = s3.create_bucket(bucket)
                if success:
                    logger.info(f"  ✓ Bucket ready: {bucket}")
                else:
                    all_ok = False
            if all_ok:
                logger.info("All S3 buckets successfully provisioned.")
                return True
        except Exception as ex:
            logger.warning(f"[Attempt {attempt}/{max_retries}] S3 endpoint not ready ({ex}). Retrying in {delay}s...")
        time.sleep(delay)

    logger.warning("Could not provision all S3 buckets within timeout. Continuing...")
    return False


if __name__ == "__main__":
    init_buckets()
