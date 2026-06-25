from typing import Optional, Any
from datetime import datetime, timezone
import hashlib
from pydantic import BaseModel, field_validator, model_validator, ConfigDict

from src.utils import generate_job_id

class RawJobPosting(BaseModel):
    model_config = ConfigDict(extra='allow')
    
    # Identity & Core fields (All optional to allow raw ingestion without errors)
    job_id_raw: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    
    # Optional raw fields
    salary_raw: Optional[str] = None
    location_raw: Optional[str] = None
    skills_raw: Optional[str] = None
    posted_date_raw: Optional[str] = None
    description: Optional[str] = None
    
    # Optional but common fields
    job_type_raw: Optional[str] = None
    experience_raw: Optional[str] = None
    
    # Additional fields from TopCV and others
    job_industry_raw: Optional[str] = None
    job_position_raw: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    job_deadline_raw: Optional[str] = None
    company_info: Optional[str] = None
    company_website: Optional[str] = None
    scraped_at: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def map_scraper_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Identity and Required fields
            if not data.get('job_id_raw') and data.get('job_id'):
                data['job_id_raw'] = data['job_id']
            if not data.get('url') and data.get('job_url'):
                data['url'] = data['job_url']
            if not data.get('company_name') and data.get('company'):
                data['company_name'] = data.get('company')
                
            # Map optional scraper fields to schema fields
            mappings = {
                'salary': 'salary_raw',
                'location': 'location_raw',
                'job_description': 'description',
                'experience_level': 'experience_raw',
                'job_type': 'job_type_raw',
                'job_industry': 'job_industry_raw',
                'job_position': 'job_position_raw',
                'job_deadline': 'job_deadline_raw'
            }
            for source_key, target_key in mappings.items():
                if not data.get(target_key) and data.get(source_key):
                    data[target_key] = data[source_key]

            if not data.get('job_id_raw') and data.get('source') and data.get('url'):
                data['job_id_raw'] = generate_job_id(data['source'], data['url'])
        return data

    def get_content_hash(self) -> str:
        raw = f"{self.title or ''}|{self.company_name or ''}|{self.salary_raw or ''}|{self.location_raw or ''}|{self.skills_raw or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_bronze_dict(self) -> dict:
        d = self.model_dump(exclude_none=False)
        d["_content_hash"] = self.get_content_hash()
        d["_scraped_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        d["_pipeline_version"] = "2.0"
        return d
