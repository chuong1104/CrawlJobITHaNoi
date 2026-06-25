"""
gold.py — Gold layer schema: dữ liệu tổng hợp dùng cho analytics / serving.
Star Schema (Fact & Dimensions) và các API/BI Data Marts.
"""
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# DIMENSION TABLES
# =============================================================================

class DimDate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    date_key: int
    full_date: date
    year: int
    quarter: int
    month: int
    day_of_month: int
    day_of_week: int
    is_weekend: bool
    is_holiday: bool = Field(default=False)
    holiday_name: Optional[str] = None


class DimCompany(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    company_key: int
    silver_company_id: int
    company_name: str
    industry: Optional[str] = None
    company_size_category: Optional[str] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None
    is_current: bool = Field(default=True)


class DimSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    skill_key: int
    silver_skill_id: int
    skill_name: str
    skill_category: Optional[str] = None
    is_tech_skill: bool = Field(default=True)


class DimLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    location_key: int
    silver_location_id: int
    location_name: str
    region: Optional[str] = None


class DimSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    source_key: int
    silver_source_id: int
    source_name: str
    base_url: Optional[str] = None


class DimJobAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    attribute_key: int
    job_level: Optional[str] = None
    job_type: Optional[str] = None
    work_mode: Optional[str] = None


# =============================================================================
# FACT TABLES
# =============================================================================

class FctJobPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    job_posting_fact_id: int
    
    # Business Keys
    silver_job_id: int
    silver_snapshot_id: int
    
    # Dimension Keys
    posted_date_key: int
    company_key: int
    source_key: int
    attribute_key: int
    
    # Measures
    salary_min_vnd: Optional[float] = None
    salary_max_vnd: Optional[float] = None
    salary_midpoint_vnd: Optional[float] = None
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    skill_count: int = Field(default=0)
    
    # Flags
    is_active: bool
    is_intern: bool = Field(default=False)
    is_fresher: bool = Field(default=False)
    has_salary: bool = Field(default=False)
    
    loaded_at: datetime


class BridgeJobSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    bridge_id: int
    job_posting_fact_id: int
    skill_key: int


class BridgeJobLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    bridge_id: int
    job_posting_fact_id: int
    location_key: int


# =============================================================================
# DATA MARTS (API & BI & ML)
# =============================================================================

class LatestJobsFlatAPI(BaseModel):
    """View phẳng dành cho Backend API (phục vụ tìm kiếm nhanh)"""
    model_config = ConfigDict(extra="forbid")
    
    id: int
    job_title: str
    company_name: str
    industry: Optional[str] = None
    source_name: str
    job_level: Optional[str] = None
    job_type: Optional[str] = None
    work_mode: Optional[str] = None
    salary_display: Optional[str] = None
    salary_min_vnd: Optional[float] = None
    salary_max_vnd: Optional[float] = None
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    deadline_date: Optional[date] = None
    canonical_url: str
    is_current: bool
    skills: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)


class DemandTrendMart(BaseModel):
    """Data Mart phân tích xu hướng tuyển dụng (BI)"""
    model_config = ConfigDict(extra="forbid")
    
    year: int
    month: int
    industry: Optional[str] = None
    total_jobs: int


class SalaryByCompanyMart(BaseModel):
    """Data Mart phân tích lương theo công ty (BI)"""
    model_config = ConfigDict(extra="forbid")
    
    company_name: str
    industry: Optional[str] = None
    avg_salary: Optional[float] = None
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None


class JobFeaturesML(BaseModel):
    """Data Mart dành cho Machine Learning (Feature Engineering)"""
    model_config = ConfigDict(extra="forbid")
    
    job_id: int
    industry: Optional[str] = None
    company_size_category: Optional[str] = None
    experience_min_years: Optional[int] = None
    is_intern: bool
    is_fresher: bool
    label_salary: Optional[float] = None
