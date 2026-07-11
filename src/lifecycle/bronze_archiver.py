import os
import re
import logging
import shutil
from datetime import datetime, timedelta
import duckdb
from botocore.config import Config

from src.storage.s3_client import S3ClientWrapper
from src.config import DATA_BRONZE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RETENTION_DAYS = 30
BRONZE_BUCKET = "jobit-bronze"
ARCHIVE_BUCKET = "jobit-bronze-archive"

def archive_old_bronze_partitions(days_to_keep=RETENTION_DAYS):
    """
    Quét bucket Bronze để tìm các thư mục chứa dữ liệu cũ hơn days_to_keep.
    Dùng DuckDB để chuyển tất cả file JSON thành Parquet (nén ZSTD) và lưu vào bucket Archive.
    Sau đó xóa các file JSON cũ đi.
    """
    s3_wrapper = S3ClientWrapper()
    s3_client = s3_wrapper.client
    
    # Đảm bảo bucket archive đã tồn tại
    s3_wrapper.create_bucket(ARCHIVE_BUCKET)
    
    # Tính ngày chốt (cutoff_date)
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    logger.info(f"Cutoff Date (giữ lại data mới hơn ngày này): {cutoff_date.date()}")
    
    # 1. Nhận diện các partition trong bucket
    paginator = s3_client.get_paginator('list_objects_v2')
    partitions = set()
    
    try:
        for page in paginator.paginate(Bucket=BRONZE_BUCKET):
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    # Ví dụ: source=topcv/year=2024/month=05/day=01/data.json
                    if "day=" in key:
                        parts = key.split("/")
                        prefix_parts = []
                        for p in parts:
                            prefix_parts.append(p)
                            if p.startswith("day="):
                                break
                        partition_prefix = "/".join(prefix_parts) + "/"
                        partitions.add(partition_prefix)
    except Exception as e:
        logger.error(f"Lỗi khi list objects trong bucket {BRONZE_BUCKET}: {e}")
        return

    logger.info(f"Tìm thấy {len(partitions)} thư mục (partition) trong {BRONZE_BUCKET}.")
    
    # Lọc các partition cũ hơn cutoff_date
    partitions_to_archive = []
    for p in partitions:
        match = re.search(r'year=(\d{4})/month=(\d{2})/day=(\d{2})', p)
        if match:
            try:
                y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                p_date = datetime(y, m, d)
                if p_date < cutoff_date:
                    partitions_to_archive.append(p)
            except ValueError:
                pass
                
    if not partitions_to_archive:
        logger.info("Không có partition nào cũ hơn cấu hình. Bỏ qua.")
        return
        
    logger.info(f"Các partition sẽ được gom và nén (Archive): {partitions_to_archive}")
    
    # 2. Cấu hình DuckDB
    logger.info("Khởi tạo DuckDB và nạp AWS credentials...")
    con = duckdb.connect()
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    
    endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    endpoint_stripped = endpoint.replace("http://", "").replace("https://", "")
    use_ssl = "true" if endpoint.startswith("https") else "false"
    
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "test")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    
    con.execute(f"SET s3_endpoint='{endpoint_stripped}';")
    con.execute(f"SET s3_access_key_id='{access_key}';")
    con.execute(f"SET s3_secret_access_key='{secret_key}';")
    con.execute(f"SET s3_region='{region}';")
    con.execute(f"SET s3_use_ssl={use_ssl};")
    con.execute("SET s3_url_style='path';") # Bắt buộc đối với Floci/LocalStack

    # 3. Tiến hành Compress & Purge
    for p in partitions_to_archive:
        logger.info(f"Đang xử lý partition: {p}")
        
        # Mẫu đầu vào và đầu ra
        input_pattern = f"s3://{BRONZE_BUCKET}/{p}*.json*"
        output_file = f"s3://{ARCHIVE_BUCKET}/{p}archive.parquet"
        
        try:
            # Gom file JSON thành Parquet nén ZSTD
            # Sử dụng ignore_errors=true để bỏ qua các dòng JSON bị lỗi cấu trúc nếu có
            query = f"""
            COPY (
                SELECT * FROM read_json_auto('{input_pattern}', ignore_errors=true)
            ) TO '{output_file}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
            con.execute(query)
            logger.info(f"Đã tạo Parquet Archive tại: {output_file}")
            
            # Xác minh file Archive đã thực sự tồn tại
            archive_keys = s3_wrapper.list_objects(ARCHIVE_BUCKET, prefix=p)
            if not any(k.endswith(".parquet") for k in archive_keys):
                raise Exception("Không tìm thấy file Parquet sau khi chạy COPY.")
                
            # Purge (Xóa) các file JSON gốc để tiết kiệm dung lượng
            objects_to_delete = s3_wrapper.list_objects(BRONZE_BUCKET, prefix=p)
            if objects_to_delete:
                # Xóa theo batch tối đa 1000 items mỗi lần gọi
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    delete_request = {'Objects': [{'Key': k} for k in batch]}
                    s3_client.delete_objects(Bucket=BRONZE_BUCKET, Delete=delete_request)
                
                logger.info(f"Đã xóa {len(objects_to_delete)} file thô gốc trong {p}")
                
            # 4. Xóa luôn file JSONL cache trên Local Disk (để tránh phình ổ cứng)
            _purge_local_jsonl(p)
                
        except Exception as e:
            logger.error(f"Lỗi khi xử lý partition {p}: {e}")

def _purge_local_jsonl(partition_path: str):
    """
    Xóa thư mục cache JSONL trên local disk ứng với partition_path.
    Ví dụ: partition_path = 'topcv/year=2024/month=05/day=01/'
    Sẽ chuyển thành -> data/bronze/topcv/2024-05-01 và xóa toàn bộ.
    """
    match = re.search(r'([^/]+)/year=(\d{4})/month=(\d{2})/day=(\d{2})/?', partition_path)
    if not match:
        return
        
    source = match.group(1)
    y, m, d = match.group(2), match.group(3), match.group(4)
    local_date_str = f"{y}-{m}-{d}"
    
    local_dir = DATA_BRONZE_DIR / source / local_date_str
    if local_dir.exists() and local_dir.is_dir():
        try:
            shutil.rmtree(local_dir)
            logger.info(f"Đã dọn dẹp Local Cache JSONL cũ: {local_dir}")
        except Exception as e:
            logger.warning(f"Không thể xóa thư mục local {local_dir}: {e}")

if __name__ == "__main__":
    archive_old_bronze_partitions(days_to_keep=RETENTION_DAYS)
