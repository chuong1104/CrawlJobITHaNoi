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

    def append_local_batch(
        self,
        source: str,
        date_str: str,
        records: List[Dict[str, Any]],
    ) -> tuple[int, int]:
        """
        Validates a batch of records and appends them to local JSONL files.
        Returns: (num_valid, num_rejected)
        """
        if not records:
            return 0, 0

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
            f"[{source}] Batch validation: {len(valid_records)} valid, {len(rejected_records)} rejected."
        )

        # --- Local paths ---
        source_dir = ensure_dir(self.local_bronze_dir / source / date_str)
        valid_file    = source_dir / f"{source}_{date_str}_valid.jsonl"
        rejected_file = source_dir / f"{source}_{date_str}_rejected.jsonl"

        # --- Append to files ---
        if valid_records:
            self._append_jsonl(valid_file, valid_records)
        if rejected_records:
            self._append_jsonl(rejected_file, rejected_records)

        return len(valid_records), len(rejected_records)

    def finalize_and_upload(
        self,
        source: str,
        date_str: str,
        total_scraped: int,
        total_validated: int,
        total_rejected: int,
        scrape_duration_seconds: float = 0.0,
    ) -> bool:
        """
        Calculates metadata, writes meta.json, and uploads the directory to S3.
        """
        logger.info(f"[{source}] Finalizing... Scraped: {total_scraped}, Valid: {total_validated}")
        now = datetime.now(timezone.utc)

        source_dir = ensure_dir(self.local_bronze_dir / source / date_str)
        valid_file    = source_dir / f"{source}_{date_str}_valid.jsonl"
        rejected_file = source_dir / f"{source}_{date_str}_rejected.jsonl"
        meta_file     = source_dir / f"{source}_{date_str}_meta.json"

        # --- Metadata ---
        file_size    = valid_file.stat().st_size if valid_file.exists() else 0
        md5_checksum = self._calculate_md5(valid_file) if valid_file.exists() else ""
        rejection_rate = (total_rejected / total_scraped * 100) if total_scraped > 0 else 0

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

        s3_valid_key    = f"{source}/{date_str}/{valid_file.name}"
        s3_rejected_key = f"{source}/{date_str}/{rejected_file.name}"
        s3_meta_key     = f"{source}/{date_str}/{meta_file.name}"

        upload_success = True
        if valid_file.exists():
            if not self.s3_client.upload_file(valid_file, self.s3_bucket, s3_valid_key):
                upload_success = False
        if rejected_file.exists():
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
