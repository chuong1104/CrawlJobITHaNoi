import os
from pathlib import Path
from src.storage.s3_client import S3ClientWrapper

s3 = S3ClientWrapper()
print("=== S3 BUCKETS CHECK ===")
for b in ["jobit-bronze", "jobit-silver", "jobit-gold", "jobit-bronze-archive"]:
    try:
        objs = s3.list_objects(b)
        print(f"Bucket {b}: {len(objs)} objects")
        if objs:
            for obj in objs[:5]:
                print(f"  - {obj}")
            if len(objs) > 5:
                print(f"  ... and {len(objs)-5} more")
    except Exception as e:
        print(f"Bucket {b}: error {e}")

print("\n=== LOCAL DATA SUMMARY ===")
base_data = Path("/opt/airflow/data")
for sub in ["bronze", "silver", "gold", "mart_bi", "mart_ml"]:
    p = base_data / sub
    if p.exists():
        files = list(p.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        parquet_count = sum(1 for f in files if f.is_file() and f.suffix == ".parquet")
        jsonl_count = sum(1 for f in files if f.is_file() and f.suffix == ".jsonl")
        print(f"{sub:10s}: {file_count} files total ({parquet_count} parquet, {jsonl_count} jsonl)")
