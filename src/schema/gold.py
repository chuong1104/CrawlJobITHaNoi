"""
gold.py — Gold layer schema: dữ liệu tổng hợp dùng cho analytics / serving.

TODO: Implement khi xây dựng Gold mart pipeline.
"""
from typing import Optional
from datetime import date
from pydantic import BaseModel, ConfigDict


class SkillDemandMetric(BaseModel):
    """Số lượng job yêu cầu từng skill theo ngày."""
    model_config = ConfigDict(extra="forbid")

    report_date: date
    skill: str
    job_count: int
    source_count: int               # Số nguồn có skill này


class SalaryBenchmark(BaseModel):
    """Benchmark lương theo title / location."""
    model_config = ConfigDict(extra="forbid")

    report_date: date
    title_normalized: str
    location: Optional[str] = None
    salary_p25: Optional[float] = None   # VND
    salary_median: Optional[float] = None
    salary_p75: Optional[float] = None
    sample_size: int
