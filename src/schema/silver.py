"""
silver.py — Silver layer schema: Cơ sở dữ liệu nghiệp vụ chuẩn hóa (Operational Database - 3NF).
Quản lý vòng đời tin tuyển dụng, SCD Type 2 cho lịch sử, và các bảng tham chiếu.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    UPDATED = "UPDATED"
    EXPIRED = "EXPIRED"
    NOT_FOUND = "NOT_FOUND"
    CLOSED = "CLOSED"
    REPOSTED = "REPOSTED"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"


class Company(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    company_id: str
    canonical_name: str
    industry: Optional[str] = None
    company_size: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CompanyAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    alias_id: str
    company_id: str
    alias_name: str


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    skill_id: str
    canonical_name: str
    category: Optional[str] = None


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    location_id: str
    canonical_name: str
    region: Optional[str] = None


class JobDuplicateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    group_id: str
    canonical_job_id: str
    created_at: datetime


class JobDuplicateGroupMember(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    group_id: str
    job_id: str
    similarity_score: float
    joined_at: datetime


class JobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    event_id: str
    job_id: str
    event_type: str
    event_time: datetime
    source_id: str
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class Job(BaseModel):
    """
    Bảng tin tuyển dụng chính (jobs) - Lưu thông tin định danh tĩnh và vòng đời.
    """
    model_config = ConfigDict(extra="forbid")
    
    job_id: str
    source_id: str
    source_job_id: Optional[str] = None
    canonical_url: str
    company_id: Optional[str] = None
    
    identity_hash: str
    latest_content_hash: str
    
    job_status: JobStatus
    is_active: bool
    
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    
    not_found_count: int = Field(default=0)
    inactive_reason: Optional[str] = None
    
    duplicate_group_id: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime


class JobSnapshot(BaseModel):
    """
    Bảng phiên bản tin tuyển dụng (job_snapshots) - SCD Type 2 cho thông tin động.
    """
    model_config = ConfigDict(extra="forbid")
    
    snapshot_id: str
    job_id: str
    
    # Dynamic Fields
    title_raw: Optional[str] = None
    title_clean: str
    company_normalized: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "VND"
    is_salary_negotiable: bool = Field(default=False)
    
    experience_raw: Optional[str] = None
    experience_years_min: Optional[int] = None
    experience_years_max: Optional[int] = None
    
    job_type: Optional[str] = None
    job_level: Optional[str] = None
    work_mode: Optional[str] = None
    
    deadline_raw: Optional[str] = None
    deadline_date: Optional[datetime] = None
    
    # N-N Relationships via Lists for Python simplicity (map to junction tables in DB)
    skills: Optional[List[str]] = Field(default_factory=list)      # List of skill_ids
    locations: Optional[List[str]] = Field(default_factory=list)   # List of location_ids
    
    # SCD Type 2 tracking
    content_hash: str
    is_current: bool
    valid_from: datetime
    valid_to: Optional[datetime] = None
    
    created_at: datetime
