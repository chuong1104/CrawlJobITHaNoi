import logging
from src.aws.s3_client import S3ClientWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aws.init_s3")

def init_buckets():
    s3 = S3ClientWrapper()
    buckets = ["jobit-bronze", "jobit-silver", "jobit-gold"]
    
    logger.info("Initializing Lakehouse S3 Buckets on Floci...")
    for bucket in buckets:
        success = s3.create_bucket(bucket)
        if success:
            logger.info(f"Successfully provisioned/verified bucket: {bucket}")
        else:
            logger.error(f"Failed to provision bucket: {bucket}")

if __name__ == "__main__":
    init_buckets()
