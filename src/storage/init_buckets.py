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


def init_buckets() -> None:
    s3 = S3ClientWrapper()
    logger.info("Initializing Lakehouse S3 Buckets on Floci...")
    for bucket in BUCKETS:
        success = s3.create_bucket(bucket)
        if success:
            logger.info(f"  ✓ Bucket ready: {bucket}")
        else:
            logger.error(f"  ✗ Failed to provision bucket: {bucket}")


if __name__ == "__main__":
    init_buckets()
