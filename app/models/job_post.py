from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base

from datetime import datetime
from typing import Optional

Base = declarative_base()
# Define the JobPost model
# This model represents a job post scraped from a website.
class JobPost(Base):
    __tablename__ = "job_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    snippet = Column(String)
    link = Column(String, unique=True)
    original_link = Column(String, nullable=True)  # Keep original link if different
    posted_time = Column(DateTime)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    keywords = Column(ARRAY(String))  # Use ARRAY for PostgreSQL

    location: Optional[str] = Column(String, nullable=True)  # Made location optional
    company = Column(String, nullable=True)  # Optional company name
    source = Column(String, nullable=False)  # Source of the job post (e.g., "GoogleSearch")

    validated = Column(Boolean, nullable=False, default=False)  # Mark if job was validated
    validated_date = Column(DateTime, nullable=True)  # Date when the job was validated
    
    status = Column(String, nullable=True, default="pending")  # e.g. "valid", "error", "skipped"


    requirements = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)

    fields_updated = Column(ARRAY(String))
    last_validated_by = Column(String)
    validation_notes = Column(Text)


    is_user_reported = Column(Boolean, default=False)  # Keep for fast filtering