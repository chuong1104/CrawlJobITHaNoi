import os
import logging
from pathlib import Path
from typing import Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger("storage.s3_client")


class S3ClientWrapper:
    def __init__(self):
        # Read configs from environment variables
        self.endpoint_url = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "test")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
        self.region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

        # Configure boto3 client
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
            config=Config(signature_version="s3v4")
        )
        logger.info(f"Initialized S3 Client targeting endpoint: {self.endpoint_url}")

    def create_bucket(self, bucket_name: str) -> bool:
        """Create bucket if it does not exist."""
        try:
            # Check if bucket already exists
            self.client.head_bucket(Bucket=bucket_name)
            logger.info(f"Bucket '{bucket_name}' already exists.")
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            # If bucket doesn't exist (404), create it
            if error_code in ("404", "NoSuchBucket"):
                try:
                    logger.info(f"Creating S3 Bucket: {bucket_name}")
                    if self.region_name == "us-east-1":
                        self.client.create_bucket(Bucket=bucket_name)
                    else:
                        self.client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": self.region_name}
                        )
                    return True
                except Exception as ex:
                    logger.error(f"Failed to create bucket '{bucket_name}': {ex}")
                    return False
            else:
                logger.error(f"Error checking bucket '{bucket_name}': {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected connection error with S3 endpoint for bucket '{bucket_name}': {e}")
            return False

    def upload_file(self, local_file_path: Path | str, bucket_name: str, object_name: str) -> bool:
        """Upload a local file to S3 bucket."""
        local_path = Path(local_file_path)
        if not local_path.exists():
            logger.error(f"Local file does not exist: {local_path}")
            return False

        try:
            logger.info(f"Uploading {local_path} to s3://{bucket_name}/{object_name}")
            self.client.upload_file(str(local_path), bucket_name, object_name)
            return True
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to s3://{bucket_name}/{object_name}: {e}")
            return False

    def list_objects(self, bucket_name: str, prefix: str = "") -> list[str]:
        """List object keys in the bucket matching the prefix."""
        try:
            response = self.client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
            keys = [content["Key"] for content in response.get("Contents", [])]
            return keys
        except Exception as e:
            logger.error(f"Failed to list objects in '{bucket_name}' with prefix '{prefix}': {e}")
            return []
