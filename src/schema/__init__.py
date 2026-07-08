"""
schema — Pydantic data contracts cho từng Medallion layer.

  bronze.py — RawJobPosting (validated raw scrape output)
  silver.py — CleanedJobPosting (normalized, deduplicated)
  gold.py   — AggregatedJobMetrics (serving layer)
"""
from src.schema.bronze import RawJobPosting

__all__ = ["RawJobPosting"]
