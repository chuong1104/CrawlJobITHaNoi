"""
delta_manager.py — Quản lý Delta Lake Tables trên S3 (Floci/LocalStack).

Thay thế hoàn toàn Parquet "raw" files bằng Delta format để có:
  - ACID Transactions: Không bao giờ corrupt khi pipeline fail
  - Time Travel: Đọc lại dữ liệu bất kỳ version nào
  - Schema Evolution: Thêm column mới mà không break pipeline
  - DuckDB Integration: delta_scan() đọc trực tiếp không cần convert

Thiết kế:
  - Một Delta Table per source (topcv, itviec, linkedin, ...)
  - Partition theo `batch_date` để tối ưu filter pushdown
  - Mỗi lần scrape: `write_deltalake(mode='append')`
  - Giữ history 30 ngày, VACUUM retention 7 ngày
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import pandas as pd
import pyarrow as pa

logger = logging.getLogger("storage.delta_manager")

# ---------------------------------------------------------------------------
# Storage options for LocalStack / Floci S3
# ---------------------------------------------------------------------------
def _get_storage_options() -> dict[str, str]:
    """Trả về storage options tương thích với Floci (LocalStack S3)."""
    endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    return {
        "endpoint": endpoint,
        "AWS_ENDPOINT_URL": endpoint,
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "test"),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", "test"),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        "allow_http": "true",
        "AWS_ALLOW_HTTP": "true",
        "AWS_VIRTUAL_HOSTED_STYLE_REQUEST": "false",
        "aws_virtual_hosted_style_request": "false",
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
        "aws_s3_allow_unsafe_rename": "true",
    }


class DeltaLakeManager:
    """
    Quản lý toàn bộ vòng đời của Delta Tables trên S3.

    Path convention:
        s3://{bucket}/bronze/{source}/         → Raw scraped data
        s3://{bucket}/gold/mart_bi/{table}/    → BI exports
        s3://{bucket}/gold/mart_ml/{table}/    → ML feature exports
    """

    BRONZE_BUCKET = os.getenv("BRONZE_BUCKET", "jobit-bronze")
    GOLD_BUCKET = os.getenv("GOLD_BUCKET", "jobit-gold")

    # Số ngày giữ lịch sử trước khi VACUUM xóa
    VACUUM_RETENTION_HOURS = int(os.getenv("DELTA_VACUUM_RETENTION_HOURS", "168"))  # 7 ngày

    def __init__(self):
        self._storage_opts = _get_storage_options()

    # ------------------------------------------------------------------
    # Private: import deltalake lazily (tránh lỗi nếu chưa cài)
    # ------------------------------------------------------------------
    @staticmethod
    def _dl():
        """Lazy import deltalake để dễ mock trong test."""
        try:
            import deltalake
            return deltalake
        except ImportError:
            raise ImportError(
                "Package 'deltalake' chưa được cài. Chạy: pip install deltalake>=0.17.0"
            )

    # ------------------------------------------------------------------
    # Bronze: ghi dữ liệu raw
    # ------------------------------------------------------------------
    def write_bronze(
        self,
        source: str,
        records: list[dict[str, Any]],
        batch_date: Optional[str] = None,
        mode: str = "append",
    ) -> int:
        """
        Ghi một batch dữ liệu raw vào Delta Table của source tương ứng.

        Args:
            source:     Tên nguồn (topcv, itviec, linkedin, ...)
            records:    List các dict đã qua Pydantic validation
            batch_date: Ngày scrape (YYYY-MM-DD). Mặc định: hôm nay
            mode:       "append" (mặc định) hoặc "overwrite"

        Returns:
            Số records đã ghi
        """
        if not records:
            logger.warning(f"[{source}] write_bronze(): 0 records — skipped.")
            return 0

        dl = self._dl()
        batch_date = batch_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Thêm metadata columns vào mỗi record
        enriched = []
        for rec in records:
            row = dict(rec)
            row["_batch_date"] = batch_date
            row["_ingested_at"] = datetime.now(timezone.utc).isoformat()
            row["_source"] = source
            enriched.append(row)

        df = pd.DataFrame(enriched)

        # Đảm bảo _batch_date là string để partition đúng
        df["_batch_date"] = df["_batch_date"].astype(str)

        from src.config import DATA_BRONZE_DIR
        local_path = DATA_BRONZE_DIR / source / "_delta"
        local_path.mkdir(parents=True, exist_ok=True)

        try:
            dl.write_deltalake(
                table_or_uri=str(local_path),
                data=df,
                mode=mode,
                partition_by=["_batch_date"],
                schema_mode="merge",   # Schema evolution: merge new columns tự động
            )
            # Upload local delta files to S3 Gold
            from src.storage.s3_client import S3ClientWrapper
            s3_client = S3ClientWrapper()
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(local_path)
                    s3_key = f"bronze/{source}/{relative_path.as_posix()}"
                    s3_client.upload_file(file_path, self.BRONZE_BUCKET, s3_key)
            logger.info(
                f"[{source}]  Wrote {len(enriched)} records to Delta "
                f"(batch_date={batch_date}, mode={mode}) and synced to S3"
            )
            return len(enriched)

        except Exception as exc:
            logger.error(f"[{source}]  Failed to write Delta Bronze: {exc}")
            raise

    # ------------------------------------------------------------------
    # Bronze: đọc dữ liệu (với Time Travel support)
    # ------------------------------------------------------------------
    def read_bronze(
        self,
        source: str,
        batch_date: Optional[str] = None,
        version: Optional[int] = None,
        as_of: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Đọc Delta Table của source, hỗ trợ Time Travel.

        Args:
            source:     Tên nguồn
            batch_date: Lọc theo ngày cụ thể (partition filter)
            version:    Time Travel theo version number
            as_of:      Time Travel theo timestamp

        Returns:
            DataFrame với toàn bộ records (hoặc theo filter)
        """
        dl = self._dl()
        table_path = f"s3://{self.BRONZE_BUCKET}/bronze/{source}"

        try:
            # Time Travel
            if version is not None:
                dt = dl.DeltaTable(table_path, storage_options=self._storage_opts, version=version)
                logger.info(f"[{source}] Time Travel to version={version}")
            elif as_of is not None:
                dt = dl.DeltaTable(table_path, storage_options=self._storage_opts)
                # Tìm version gần nhất trước as_of timestamp
                history = dt.history()
                target_version = _find_version_as_of(history, as_of)
                dt = dl.DeltaTable(table_path, storage_options=self._storage_opts, version=target_version)
                logger.info(f"[{source}] Time Travel to as_of={as_of} (version={target_version})")
            else:
                dt = dl.DeltaTable(table_path, storage_options=self._storage_opts)

            # Partition filter: chỉ đọc batch_date cụ thể nếu có
            if batch_date:
                df = dt.to_pandas(filters=[("_batch_date", "=", batch_date)])
            else:
                df = dt.to_pandas()

            logger.info(f"[{source}] Read {len(df)} records from Delta Bronze.")
            return df

        except Exception as exc:
            logger.error(f"[{source}]  Failed to read Delta Bronze: {exc}")
            raise

    # ------------------------------------------------------------------
    # Bronze: lấy metadata & history
    # ------------------------------------------------------------------
    def get_table_history(self, source: str, limit: int = 10) -> list[dict]:
        """Trả về lịch sử commit của Delta Table (dùng cho audit/debug)."""
        dl = self._dl()
        table_path = f"s3://{self.BRONZE_BUCKET}/bronze/{source}"
        try:
            dt = dl.DeltaTable(table_path, storage_options=self._storage_opts)
            history = dt.history(limit=limit)
            return history
        except Exception as exc:
            logger.error(f"[{source}] Cannot get history: {exc}")
            return []

    def get_current_version(self, source: str) -> Optional[int]:
        """Trả về version hiện tại của Delta Table."""
        dl = self._dl()
        table_path = f"s3://{self.BRONZE_BUCKET}/bronze/{source}"
        try:
            dt = dl.DeltaTable(table_path, storage_options=self._storage_opts)
            return dt.version()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Gold: ghi export marts
    # ------------------------------------------------------------------
    def write_gold_mart(
        self,
        mart_name: str,
        table_name: str,
        df: pd.DataFrame,
        mode: str = "overwrite",
    ) -> int:
        """
        Ghi DataFrame vào Gold Delta Table (mart_bi hoặc mart_ml).

        Args:
            mart_name:  "mart_bi" hoặc "mart_ml"
            table_name: Tên bảng (agg_demand_trend, job_features, ...)
            df:         DataFrame cần ghi
            mode:       "overwrite" (default, cập nhật toàn bộ mỗi ngày)
        """
        if df.empty:
            logger.warning(f"[{mart_name}/{table_name}] Empty DataFrame — skipped.")
            return 0

        dl = self._dl()

        # Thêm export timestamp
        df = df.copy()
        df["_exported_at"] = datetime.now(timezone.utc).isoformat()

        from src.config import DATA_GOLD_DIR
        local_path = DATA_GOLD_DIR / mart_name / table_name
        local_path.mkdir(parents=True, exist_ok=True)

        try:
            dl.write_deltalake(
                table_or_uri=str(local_path),
                data=df,
                mode=mode,
                schema_mode="overwrite",  # Gold được overwrite hoàn toàn mỗi ngày
            )
            # Upload local delta files to S3
            from src.storage.s3_client import S3ClientWrapper
            s3_client = S3ClientWrapper()
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(DATA_GOLD_DIR)
                    s3_key = f"gold/{relative_path.as_posix()}"
                    s3_client.upload_file(file_path, self.GOLD_BUCKET, s3_key)
            logger.info(
                f"[Gold]  Wrote {len(df)} rows to Delta "
                f"s3://{self.GOLD_BUCKET}/gold/{mart_name}/{table_name} (via local write and sync)"
            )
            return len(df)

        except Exception as exc:
            logger.error(f"[Gold]  Failed to write {mart_name}/{table_name}: {exc}")
            raise

    # ------------------------------------------------------------------
    # Maintenance: VACUUM + Compact
    # ------------------------------------------------------------------
    def vacuum_table(self, source: str, layer: str = "bronze") -> str:
        """
        Chạy VACUUM để xóa các file cũ quá retention period.
        Giữ lại lịch sử VACUUM_RETENTION_HOURS giờ (default: 7 ngày).

        Args:
            source: Tên nguồn hoặc mart table
            layer:  "bronze" hoặc "gold"
        """
        dl = self._dl()
        from src.config import DATA_BRONZE_DIR, DATA_GOLD_DIR

        if layer == "bronze":
            table_path = f"s3://{self.BRONZE_BUCKET}/bronze/{source}"
            local_path = DATA_BRONZE_DIR / source / "_delta"
        else:
            table_path = f"s3://{self.GOLD_BUCKET}/gold/{source}"
            local_path = DATA_GOLD_DIR / source

        try:
            # 1. Vacuum trên S3 (Floci)
            dt_s3 = dl.DeltaTable(table_path, storage_options=self._storage_opts)
            deleted_s3 = dt_s3.vacuum(
                retention_hours=self.VACUUM_RETENTION_HOURS,
                dry_run=False,
                enforce_retention_duration=False,  # Cho phép retention < 7 ngày trong dev
            )
            msg = (
                f"[{layer}/{source}] S3 VACUUM: "
                f"deleted {len(deleted_s3)} stale files."
            )
            
            # 2. Vacuum trên Local Disk (Cache)
            if local_path.exists():
                try:
                    dt_local = dl.DeltaTable(str(local_path))
                    deleted_local = dt_local.vacuum(
                        retention_hours=self.VACUUM_RETENTION_HOURS,
                        dry_run=False,
                        enforce_retention_duration=False,
                    )
                    msg += f" | Local VACUUM: deleted {len(deleted_local)} files."
                except Exception as local_exc:
                    logger.warning(f"[{layer}/{source}] Local VACUUM skipped: {local_exc}")

            logger.info(msg)
            return msg
        except Exception as exc:
            logger.warning(f"[{layer}/{source}] S3 VACUUM skipped (table may not exist yet): {exc}")
            return f"VACUUM skipped: {exc}"

    def vacuum_all_bronze(self, sources: list[str]) -> dict[str, str]:
        """Chạy VACUUM cho tất cả Bronze Delta Tables."""
        results = {}
        for source in sources:
            results[source] = self.vacuum_table(source, layer="bronze")
        return results

    def optimize_table(self, source: str, layer: str = "bronze") -> dict:
        """
        Compact nhiều file nhỏ thành file lớn hơn (Z-ORDER optimization).
        Cải thiện read performance cho DuckDB.
        """
        dl = self._dl()

        if layer == "bronze":
            table_path = f"s3://{self.BRONZE_BUCKET}/bronze/{source}"
        else:
            table_path = f"s3://{self.GOLD_BUCKET}/gold/{source}"

        try:
            dt = dl.DeltaTable(table_path, storage_options=self._storage_opts)
            result = dt.optimize.compact()
            logger.info(f"[{layer}/{source}] OPTIMIZE compact: {result}")
            return result
        except Exception as exc:
            logger.warning(f"[{layer}/{source}] OPTIMIZE skipped: {exc}")
            return {}

    # ------------------------------------------------------------------
    # DuckDB Integration helpers
    # ------------------------------------------------------------------
    def get_duckdb_scan_query(self, source: str, layer: str = "bronze") -> str:
        """
        Trả về câu SQL để DuckDB đọc Delta Table trực tiếp từ S3.

        Sử dụng: conn.execute(manager.get_duckdb_scan_query('topcv'))
        """
        if layer == "bronze":
            path = f"s3://{self.BRONZE_BUCKET}/bronze/{source}"
        else:
            path = f"s3://{self.GOLD_BUCKET}/gold/{source}"

        # DuckDB cần delta extension (cài trong profiles.yml)
        return f"SELECT * FROM delta_scan('{path}')"

    def setup_duckdb_s3(self, conn) -> None:
        """
        Cấu hình DuckDB connection để connect với Floci/LocalStack S3.
        Gọi một lần trước khi chạy bất kỳ delta_scan() nào.
        """
        endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566").replace("http://", "")
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "test")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "test")

        conn.execute(f"""
            INSTALL delta;
            LOAD delta;
            INSTALL httpfs;
            LOAD httpfs;
            SET s3_endpoint='{endpoint}';
            SET s3_access_key_id='{access_key}';
            SET s3_secret_access_key='{secret_key}';
            SET s3_use_ssl=false;
            SET s3_url_style='path';
        """)
        logger.info("DuckDB configured for Delta + S3 access.")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _find_version_as_of(history: list[dict], as_of: datetime) -> int:
    """
    Tìm version Delta Table gần nhất TRƯỚC as_of timestamp.
    history: list của dict có key 'timestamp' và 'version'.
    """
    as_of_ts = as_of.timestamp() * 1000  # milliseconds
    best_version = 0
    for entry in history:
        entry_ts = entry.get("timestamp", 0)
        if entry_ts <= as_of_ts:
            best_version = entry.get("version", 0)
    return best_version
