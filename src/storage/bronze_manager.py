from datetime import timedelta
import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import ValidationError

from src.storage.s3_client import S3ClientWrapper
from src.storage.delta_manager import DeltaLakeManager
from src.schema.bronze import RawJobPosting
from src.utils import ensure_dir

logger = logging.getLogger("storage.bronze_manager")


class BronzeManager:
    def __init__(self, local_bronze_dir: Path, s3_bucket: str = "jobit-bronze"):
        self.local_bronze_dir = local_bronze_dir
        self.s3_bucket = s3_bucket
        self.s3_client = S3ClientWrapper()
        self.delta_manager = DeltaLakeManager()
        # Tích lũy validated records để ghi vào Delta khi finalize
        self._pending_delta_records: List[Dict[str, Any]] = []

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
            # Tích lũy để ghi Delta khi finalize
            self._pending_delta_records.extend(valid_records)
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

        # Create dummy file if scraper returned nothing, to prevent dbt IO Error
        if not valid_file.exists():
            dummy_record = {
                "job_id": None, "job_url": None, "title": None, "company": None,
                "job_description": None, "requirements": None, "location": None,
                "job_industry": None, "job_type": None, "job_position": None,
                "salary": None, "experience_level": None, "job_deadline": None,
                "scraped_at": None, "source": source
            }
            with valid_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps(dummy_record, ensure_ascii=False) + "\n")

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

        # --- Upload JSONL to S3 (backup / compatibility) ---
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

        # --- Ghi vào Delta Lake (Primary Storage) ---
        if self._pending_delta_records:
            try:
                self.delta_manager.write_bronze(
                    source=source,
                    records=self._pending_delta_records,
                    batch_date=date_str,
                    mode="append",
                )
                # Reset pending records sau khi ghi thành công
                self._pending_delta_records = []
            except Exception as exc:
                logger.error(f"[{source}] Delta write failed (JSONL backup still uploaded): {exc}")
                # Không raise — JSONL backup đã có trên S3, pipeline không bị crash
                upload_success = False

        return upload_success

    def get_recent_job_urls(self, source: str, days: int = 14) -> set[str]:
        """
        Lấy danh sách các job_url đã được cào trong N ngày gần nhất từ Delta Lake Bronze
        hoặc từ các file JSONL local làm fallback.
        Dùng cho Early Stopping và Phase 2 Dedup.
        """
        urls: set[str] = set()
        
        # 1. Thử đọc từ Delta Lake local cache
        try:
            from src.config import DATA_BRONZE_DIR
            local_delta_path = DATA_BRONZE_DIR / source / "_delta"
            if local_delta_path.exists():
                import deltalake
                dt = deltalake.DeltaTable(str(local_delta_path))
                # Lọc theo batch_date gần đây
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
                df = dt.to_pandas(filters=[("_batch_date", ">=", cutoff_date)])
                if not df.empty and "job_url" in df.columns:
                    urls.update(df["job_url"].dropna().unique())
                    logger.info(f"[{source}] Loaded {len(urls)} recent job_urls from Delta Lake (>= {cutoff_date})")
                    return urls
        except Exception as e:
            logger.debug(f"[{source}] Delta Lake read for recent URLs skipped: {e}")

        # 2. Fallback: Đọc trực tiếp từ file JSONL local
        try:
            from src.config import DATA_BRONZE_DIR
            source_dir = DATA_BRONZE_DIR / source
            if source_dir.exists():
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
                for folder in source_dir.iterdir():
                    if folder.is_dir() and folder.name >= cutoff_date and not folder.name.startswith("_"):
                        for jsonl_file in folder.glob("*_valid.jsonl"):
                            with jsonl_file.open("r", encoding="utf-8") as f:
                                for line in f:
                                    if line.strip():
                                        try:
                                            row = json.loads(line)
                                            if row.get("job_url"):
                                                urls.add(row["job_url"])
                                        except Exception:
                                            pass
                if urls:
                    logger.info(f"[{source}] Loaded {len(urls)} recent job_urls from local JSONL files")
        except Exception as e:
            logger.warning(f"[{source}] Error reading local JSONL for recent URLs: {e}")

        return urls

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
