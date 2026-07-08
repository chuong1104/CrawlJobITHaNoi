from typing import Optional, Any
from pydantic import BaseModel, model_validator, ConfigDict

from src.utils import generate_job_id


class RawJobPosting(BaseModel):
    model_config = ConfigDict(extra='allow')
    
    title: Optional[str] = None
    company: Optional[str] = None
    salary: Optional[str] = None
    location: Optional[str] = None
    experience_level: Optional[str] = None
    job_type: Optional[str] = None
    job_industry: Optional[str] = None
    job_position: Optional[str] = None
    job_description: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    job_deadline: Optional[str] = None
    company_info: Optional[str] = None
    company_website: Optional[str] = None
    job_url: Optional[str] = None
    source: Optional[str] = None
    scraped_at: Optional[str] = None
    job_id: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def set_job_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get('job_id') and data.get('source') and data.get('job_url'):
                data['job_id'] = generate_job_id(data['source'], data['job_url'])
        return data

    def to_bronze_dict(self) -> dict:
        return self.model_dump(exclude_none=False)
