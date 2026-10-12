"""
sync_data_to_s3_parquet.py — Chuyển đổi dữ liệu local sang Parquet và đồng bộ lên S3 Floci.

Hỗ trợ:
1. Chuyển đổi tất cả raw JSONL (Bronze) thành định dạng Parquet (nén Snappy/ZSTD).
2. Đồng bộ các bảng Delta Lake Parquet (cả Bronze và Gold) lên S3 Floci.
3. Đồng bộ các file Parquet Gold Marts (mart_bi, mart_ml) lên S3 Floci.
4. Tương thích chạy trực tiếp trên máy Host hoặc bên trong container Airflow:
   - Trong Docker: AWS_ENDPOINT_URL = http://floci:4566
   - Ngoài Docker (Host): AWS_ENDPOINT_URL = http://localhost:4566
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

# Thêm thư mục gốc vào PYTHONPATH nếu chưa có
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.storage.s3_client import S3ClientWrapper
from src.config import DATA_BRONZE_DIR, DATA_GOLD_DIR, DATA_MART_BI_DIR, DATA_MART_ML_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sync_data_to_parquet_s3")


class DataToParquetS3Syncer:
    def __init__(self):
        self.s3_client = S3ClientWrapper()
        self.bronze_bucket = "jobit-bronze"
        self.silver_bucket = "jobit-silver"
        self.gold_bucket = "jobit-gold"

    def ensure_buckets(self):
        """Khởi tạo đầy đủ các bucket trên Floci nếu chưa tồn tại."""
        logger.info("Kiểm tra và tạo S3 buckets trên Floci...")
        for bucket in [self.bronze_bucket, self.silver_bucket, self.gold_bucket]:
            created = self.s3_client.create_bucket(bucket)
            if created:
                logger.info(f"  ✓ S3 Bucket sẵn sàng: {bucket}")
            else:
                logger.warning(f"  ⚠ Không thể khởi tạo bucket: {bucket}")

    def convert_jsonl_to_parquet(self, jsonl_file: Path) -> Path | None:
        """Đọc file JSONL và chuyển đổi thành file Parquet song song trên local."""
        parquet_file = jsonl_file.with_suffix(".parquet")
        
        records: List[Dict[str, Any]] = []
        try:
            with jsonl_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
                            
            if not records:
                logger.warning(f"File rỗng, bỏ qua convert: {jsonl_file.name}")
                return None

            df = pd.DataFrame(records)
            
            # Chuẩn hóa các cột object / dict sang string để tránh schema mismatch trong Parquet
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else (str(x) if pd.notnull(x) else None))

            table = pa.Table.from_pandas(df)
            pq.write_table(table, parquet_file, compression="SNAPPY")
            logger.info(f"  [Convert Parquet] {jsonl_file.name} ({len(records)} dòng) -> {parquet_file.name}")
            return parquet_file
        except Exception as e:
            logger.error(f"Lỗi khi convert {jsonl_file}: {e}")
            return None

    def sync_bronze_jsonl_as_parquet(self) -> int:
        """
        Quét tất cả các file JSONL trong data/bronze, convert sang Parquet và upload lên S3.
        Key trên S3: bronze/{source}/{date}/{filename}.parquet
        """
        logger.info("\n=== BẮT ĐẦU CHUYỂN ĐỔI JSONL BRONZE -> PARQUET -> S3 ===")
        if not DATA_BRONZE_DIR.exists():
            logger.warning(f"Thư mục không tồn tại: {DATA_BRONZE_DIR}")
            return 0

        jsonl_files = list(DATA_BRONZE_DIR.rglob("*_valid.jsonl"))
        logger.info(f"Tìm thấy {len(jsonl_files)} file valid JSONL trong {DATA_BRONZE_DIR}")

        uploaded_count = 0
        for jf in jsonl_files:
            # Bỏ qua thư mục ẩn hoặc backup
            if "_delta" in jf.parts:
                continue

            parquet_file = self.convert_jsonl_to_parquet(jf)
            if parquet_file and parquet_file.exists():
                # Tạo S3 Key: ví dụ bronze/topcv/2026-10-12/topcv_2026-10-12_valid.parquet
                rel_path = parquet_file.relative_to(DATA_BRONZE_DIR)
                s3_key = f"bronze/{rel_path.as_posix()}"
                
                success = self.s3_client.upload_file(parquet_file, self.bronze_bucket, s3_key)
                if success:
                    uploaded_count += 1

        logger.info(f"✓ Đã convert và upload {uploaded_count}/{len(jsonl_files)} file Parquet Bronze lên s3://{self.bronze_bucket}/")
        return uploaded_count

    def sync_delta_tables(self) -> int:
        """
        Đồng bộ toàn bộ các bảng Delta Lake (bao gồm các file Parquet phân vùng và _delta_log)
        lên S3 Floci cho cả Bronze và Gold.
        """
        logger.info("\n=== BẮT ĐẦU ĐỒNG BỘ DELTA LAKE (PARQUET + LOGS) LÊN S3 ===")
        synced_files = 0

        # 1. Đồng bộ Bronze Delta Tables
        if DATA_BRONZE_DIR.exists():
            for delta_dir in DATA_BRONZE_DIR.glob("*/_delta"):
                source = delta_dir.parent.name
                for file_path in delta_dir.rglob("*"):
                    if file_path.is_file():
                        rel = file_path.relative_to(delta_dir)
                        s3_key = f"bronze/{source}/{rel.as_posix()}"
                        if self.s3_client.upload_file(file_path, self.bronze_bucket, s3_key):
                            synced_files += 1

        # 2. Đồng bộ Gold Delta Tables
        if DATA_GOLD_DIR.exists():
            for file_path in DATA_GOLD_DIR.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    rel = file_path.relative_to(DATA_GOLD_DIR)
                    s3_key = f"gold/{rel.as_posix()}"
                    if self.s3_client.upload_file(file_path, self.gold_bucket, s3_key):
                        synced_files += 1

        logger.info(f"✓ Đã đồng bộ {synced_files} file Delta Lake / Parquet lên S3")
        return synced_files

    def sync_gold_marts_parquet(self) -> int:
        """
        Đồng bộ các file Parquet Gold Marts (mart_bi, mart_ml) lên s3://jobit-gold/marts/
        """
        logger.info("\n=== BẮT ĐẦU ĐỒNG BỘ GOLD MARTS PARQUET LÊN S3 ===")
        synced = 0
        for mart_dir, mart_name in [(DATA_MART_BI_DIR, "mart_bi"), (DATA_MART_ML_DIR, "mart_ml")]:
            if mart_dir.exists():
                for p_file in mart_dir.glob("*.parquet"):
                    s3_key = f"gold/{mart_name}/{p_file.name}"
                    if self.s3_client.upload_file(p_file, self.gold_bucket, s3_key):
                        synced += 1

        logger.info(f"✓ Đã đồng bộ {synced} file Gold Marts Parquet lên s3://{self.gold_bucket}/")
        return synced

    def print_s3_summary(self):
        """Liệt kê các file hiện có trên các bucket S3 Floci."""
        logger.info("\n" + "=" * 60)
        logger.info("TỔNG HỢP DỮ LIỆU HIỆN CÓ TRÊN FLOCI S3:")
        logger.info("=" * 60)
        for bucket in [self.bronze_bucket, self.silver_bucket, self.gold_bucket]:
            objects = self.s3_client.list_objects(bucket)
            logger.info(f"\n📦 Bucket: s3://{bucket}/ ({len(objects)} files)")
            for obj in objects[:10]:
                logger.info(f"  • {obj}")
            if len(objects) > 10:
                logger.info(f"  ... và {len(objects) - 10} files khác.")


def main():
    syncer = DataToParquetS3Syncer()
    syncer.ensure_buckets()
    
    # 1. Convert JSONL Bronze sang Parquet & upload
    syncer.sync_bronze_jsonl_as_parquet()

    # 2. Upload các bảng Delta Lake Parquet (Bronze & Gold)
    syncer.sync_delta_tables()

    # 3. Upload Gold Marts Parquet (nếu có)
    syncer.sync_gold_marts_parquet()

    # 4. In báo cáo tổng hợp
    syncer.print_s3_summary()


if __name__ == "__main__":
    main()
