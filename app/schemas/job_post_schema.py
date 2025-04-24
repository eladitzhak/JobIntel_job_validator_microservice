# schemas/job_post.py

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
from datetime import datetime


class JobPostBase(BaseModel):
    title: str
    link: HttpUrl
    keywords: List[str]


class JobPostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=4)
    location: Optional[str] =  None
    company: Optional[str] =  None
    posted_time: Optional[datetime] =  None
    description: Optional[str] =  None
    requirements: Optional[str] =  None
    responsibilities: Optional[str] =  None
    keywords: Optional[List[str]] =  None

    @field_validator("description", "requirements", "responsibilities", mode="before")
    @classmethod
    def no_script_tags(cls, v):
        if isinstance(v, list):
            v = " ".join(v)
        if isinstance(v, str) and "<script" in v.lower():
            raise ValueError("XSS risk detected in field")
        return v

    # class Config:
    #     orm_mode = True
    model_config = {
        "from_attributes": True, 
        "extra": "forbid"
    }

class JobValidationResult(BaseModel):
    job_id: int
    validated_by: Optional[str]
    status: Optional[str]
    validated_date: Optional[str]
    update_success: bool
    fields_updated: Optional[List[str]]
    notes: Optional[str]
    job_link: str

