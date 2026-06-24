import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

from pydantic import ValidationError

from src.storage.s3_client import S3ClientWrapper
from src.schema.bronze import RawJobPosting
from src.utils import ensure_dir

logger = logging.getLogger("storage.bronze_manager")


class BronzeManager:
    def __init__(self, local_bronze_dir: Path, s3_bucket: str = "jobit-bronze"):
        self.local_bronze_dir = local_bronze_dir
        self.s3_bucket = s3_bucket
        self.s3_client = S3ClientWrapper()

    def process_and_upload(
        self,
        source: str,
        records: List[Dict[str, Any]],
        scrape_duration_seconds: float = 0.0,
    ) -> bool:
        if not records:
            logger.info(f"[{source}] No records to process for Bronze.")
            return True

        now = datetime.now(timezone.utc)
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        date_str = now.strftime("%Y-%m-%d")

        valid_records = []
        rejected_records = []

        # --- Validation ---
        for rec in records:
            try:
                parsed = RawJobPosting.model_validate(rec)
                valid_records.append(parsed.to_bronze_dict())
            except ValidationError as e:
                rejected_records.append({"original_record": rec, "error": str(e)})

        logger.info(
            f"[{source}] Validation: {len(valid_records)} valid, {len(rejected_records)} rejected."
        )

        # --- Local paths (Hive-style partitioning) ---
        partition = f"source={source}/year={year}/month={month}/day={day}"
        valid_dir    = ensure_dir(self.local_bronze_dir / "valid"    / partition)
        rejected_dir = ensure_dir(self.local_bronze_dir / "rejected" / partition)
        meta_dir     = ensure_dir(self.local_bronze_dir / "meta"     / partition)

        valid_file    = valid_dir    / f"{source}_{date_str}.jsonl"
        rejected_file = rejected_dir / f"{source}_{date_str}_rejected.jsonl"
        meta_file     = meta_dir     / f"{source}_{date_str}.meta.json"

        # --- Write files ---
        if valid_records:
            self._append_jsonl(valid_file, valid_records)
        if rejected_records:
            self._append_jsonl(rejected_file, rejected_records)

        # --- Metadata ---
        file_size    = valid_file.stat().st_size if valid_file.exists() else 0
        md5_checksum = self._calculate_md5(valid_file) if valid_file.exists() else ""
        total_scraped    = len(records)
        total_validated  = len(valid_records)
        total_rejected   = len(rejected_records)
        rejection_rate   = (total_rejected / total_scraped * 100) if total_scraped > 0 else 0

        metadata = {
            "source": source,
            "date": date_str,
            "total_scraped": total_scraped,
            "total_validated": total_validated,
            "total_rejected": total_rejected,
            "rejection_rate_pct": round(rejection_rate, 2),
            "scrape_duration_seconds": round(scrape_duration_seconds, 2),
            "file_size_bytes": file_size,
            "md5_checksum": md5_checksum,
            "processed_at": now.isoformat().replace("+00:00", "Z"),
        }
        with meta_file.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # --- Upload to S3 ---
        self.s3_client.create_bucket(self.s3_bucket)

        s3_valid_key    = f"valid/{partition}/{valid_file.name}"
        s3_rejected_key = f"rejected/{partition}/{rejected_file.name}"
        s3_meta_key     = f"meta/{partition}/{meta_file.name}"

        upload_success = True
        if valid_records:
            if not self.s3_client.upload_file(valid_file, self.s3_bucket, s3_valid_key):
                upload_success = False
        if rejected_records:
            if not self.s3_client.upload_file(rejected_file, self.s3_bucket, s3_rejected_key):
                upload_success = False
        if not self.s3_client.upload_file(meta_file, self.s3_bucket, s3_meta_key):
            upload_success = False

        return upload_success

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _append_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
        with path.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    @staticmethod
    def _calculate_md5(path: Path) -> str:
        hash_md5 = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
