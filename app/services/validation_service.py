from sqlalchemy.orm import Session
from datetime import datetime
import pytz

from app.models.job_post import JobPost
from app.db.session import SessionLocal
from app.validators.factory import ValidatorFactory
from app.config import settings
from app.log_config import logger  
from app.utils.db_utils import commit_or_rollback

class JobValidatorService:
    def __init__(self, db_session):
        self.db = db_session or SessionLocal()
        self.results = []
        self.israel_tz = pytz.timezone("Israel")

    def validate_pending_jobs(self):
        """
        Validate pending jobs in the database.
        """
        pending_jobs = self.db.query(JobPost).filter(
            JobPost.validated.is_(False),
            JobPost.status == "pending",
            JobPost.link.contains("comeet"),
        ).limit(5).all()
        if not pending_jobs:
            logger.error("No pending jobs to validate.")
            return

        for job in pending_jobs:
            logger.info(f"🔍 Validating: {job.link} id: {job.id}")
            if self.validate_job(job):
                logger.info(f"✅ Job validated: {job.link} id: {job.id}")
            else: 
                logger.error(f"❌ Job validation failed: {job.link} id: {job.id}")

    def validate_job(self, job: JobPost) -> bool:
        metadata = {}
        try:
            validator = ValidatorFactory.create_validator(job.link)
            if not validator:
                logger.warning(f"⚠️ No validator for: {job.link}")
                with commit_or_rollback(self.db, job):
                    job.status = "no validator error"
                    job.validated_date = datetime.now(self.israel_tz)
                return False

            if not validator.validate():
                logger.warning(f"❌ Validation failed: {job.link} id: {job.id}")
                with commit_or_rollback(self.db, job):
                    job.status = "error"
                    job.validated_date = datetime.now(self.israel_tz)
                return False

            metadata = validator.extract_metadata()
            logger.debug(f"📦 Metadata: {metadata}")
            self.apply_metadata(job, metadata, [
                    "title", "location", "company", 
                    "description", "posted_time", "requirements"
            ])
        
            # for key in ["title", "location", "company", "description", "posted_time", "requirements"]:
            #     if hasattr(job, key) and key in metadata:
            #         setattr(job, key, metadata[key])

            self.results.append({
                "link": job.link,
                "status": "validated",
                "metadata": metadata
            })
            #TODO move to validated function
            with commit_or_rollback(self.db, job):
                job.validated = True
                job.status = "valid"
                job.validated_date = datetime.now(self.israel_tz)
            return True

        except Exception as e:
            job.status = "error"
            job.validated_date = datetime.now(self.israel_tz)
            logger.error(f"Error validating job {job.link}: {e}")
            return False

    def run_batch(self, jobs: list[JobPost]):
        for job in jobs:
            self.validate_job(job)

    def apply_metadata(self,job, metadata, fields):
        for key in fields:
            if (
                hasattr(job, key) and 
                key in metadata and
                metadata[key] is not None
            ):
                if key == "posted_time":
                    # Convert to datetime object if it's a string
                    if isinstance(metadata[key], str):
                        try:
                            metadata[key] = datetime.strptime(metadata[key], "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
                setattr(job, key, metadata[key])



