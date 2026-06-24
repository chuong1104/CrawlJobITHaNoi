from typing import Optional, Any
from datetime import datetime, timezone
import hashlib
from pydantic import BaseModel, field_validator, model_validator, ConfigDict

from src.utils import generate_job_id

class RawJobPosting(BaseModel):
    model_config = ConfigDict(extra='allow')
    
    # Required fields
    job_id_raw: Optional[str] = None
    title: str
    company_name: str
    source: str
    url: str
    
    # Optional raw fields
    salary_raw: Optional[str] = None
    location_raw: Optional[str] = None
    skills_raw: Optional[str] = None
    posted_date_raw: Optional[str] = None
    description: Optional[str] = None
    
    # Optional but common fields
    job_type_raw: Optional[str] = None
    experience_raw: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def auto_fill_job_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Attempt to map from existing parser conventions if needed
            if not data.get('job_id_raw') and data.get('job_id'):
                data['job_id_raw'] = data['job_id']
            if not data.get('url') and data.get('job_url'):
                data['url'] = data['job_url']
                
            if not data.get('job_id_raw') and data.get('source') and data.get('url'):
                data['job_id_raw'] = generate_job_id(data['source'], data['url'])
        return data

    @field_validator('title', mode='after')
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Title must not be empty")
        return v

    @field_validator('url', mode='after')
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v or not str(v).startswith("http"):
            raise ValueError("URL must start with http")
        return v

    def get_content_hash(self) -> str:
        raw = f"{self.title}|{self.company_name}|{self.salary_raw or ''}|{self.location_raw or ''}|{self.skills_raw or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_bronze_dict(self) -> dict:
        d = self.model_dump(exclude_none=False)
        d["_content_hash"] = self.get_content_hash()
        d["_scraped_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        d["_pipeline_version"] = "2.0"
        return d
