"""
silver.py — Silver layer schema: dữ liệu đã được làm sạch, chuẩn hoá và deduplicate.

TODO: Implement khi xây dựng Silver transform pipeline.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CleanedJobPosting(BaseModel):
    """
    Silver layer model — normalized job posting.
    Populated by the Silver transform pipeline (dbt / Spark).
    """
    model_config = ConfigDict(extra="forbid")

    # Identity
    job_id: str                         # Deterministic hash từ source + url
    source: str                         # e.g. "topcv", "linkedin"
    url: str

    # Normalized fields
    title: str
    company_name: str
    location: Optional[str] = None      # Chuẩn hoá về tên tỉnh/thành
    salary_min: Optional[float] = None  # VND
    salary_max: Optional[float] = None  # VND
    salary_currency: Optional[str] = "VND"
    skills: Optional[list[str]] = None  # Danh sách skill đã tách
    job_type: Optional[str] = None      # full-time / part-time / contract
    experience_years_min: Optional[int] = None
    description: Optional[str] = None

    # Timestamps
    posted_date: Optional[datetime] = None
    scraped_at: datetime
    processed_at: Optional[datetime] = None

    # Lineage
    _content_hash: Optional[str] = None
    _pipeline_version: Optional[str] = None
