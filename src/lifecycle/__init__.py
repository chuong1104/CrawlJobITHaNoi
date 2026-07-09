"""
lifecycle — Quản lý vòng đời dữ liệu và lưu trữ.

  bronze_archiver.py   — Gom nén JSON Bronze cũ thành Parquet ZSTD trên S3
  lifecycle_manager.py — Orchestrate các task lifecycle đặc biệt (alert, review queue)
"""
from src.lifecycle.bronze_archiver import archive_old_bronze_partitions
from src.lifecycle.lifecycle_manager import LifecycleManager

__all__ = ["archive_old_bronze_partitions", "LifecycleManager"]
