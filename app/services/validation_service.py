from sqlalchemy.orm import Session
from datetime import datetime
import pytz
from urllib.parse import urlparse
from pydantic import ValidationError


from app.schemas.job_post_schema import JobPostUpdate
from app.models.job_post import JobPost
from app.db.session import SessionLocal
from app.validators.factory import ValidatorFactory
from app.config import settings
from app.log_config import logger  
from app.utils.db_utils import commit_or_rollback
from app.utils.chrome_driver_manger import DriverManager
from app.exceptions.exceptions import LocationValidationError


#TODO:INJECT DEPENDS(get_db)?
class JobValidatorService:
    def __init__(self, db_session):
        self.db = db_session or SessionLocal()
        self.results = []
        self.israel_tz = pytz.timezone("Israel")

    def is_company_page(self, url: str) -> bool:
        """
        Check if the URL is a company page and not specific job page.
        """
        # Example logic: check if the URL contains "company"
        # Check URL pattern
        path_parts = urlparse(url).path.strip('/').split('/')
        if len(path_parts) == 3:
            return True
        return False
        
    def validate_pending_jobs(self):
        """
        Validate pending jobs in the database.
        """

        pending_jobs = self.db.query(JobPost).filter(
            JobPost.validated.is_(False),
            JobPost.status == "pending",
            JobPost.link.contains("greenhouse") | JobPost.link.contains("comeet"),
            # Updated filter to include both "greenhouse" and "comeet" links
        ).limit(2).all()

        # pending_jobs = self.db.query(JobPost).filter(
        #     JobPost.id == 99,
        # ).limit(2).all()
        
        # pending_jobs = self.db.query(JobPost).filter(
        #     JobPost.link == "https://www.comeet.com/jobs/drivenets/72.006/full-stack-team-leader-node_js--react/A1.456"
        # ).limit(2).all()

        if not pending_jobs:
            logger.error("No pending jobs to validate.")
            return
        
        with DriverManager() as driver_manager:
            for job in pending_jobs:
                logger.info(f"🔍 Validating: {job.link} id: {job.id}")
                
                try:
                    validator = ValidatorFactory.create_validator(job.link)
                except Exception as e:
                    logger.warning(f"❌ No validator implemented for: {job.link}")
                    with commit_or_rollback(self.db, job):
                        job.validated = True
                        job.status = "no validator"
                        job.validated_date = datetime.now(self.israel_tz)
                    continue
                if not validator:
                    logger.warning(f"⚠️ No validator for: {job.link}")
                    with commit_or_rollback(self.db, job):
                        job.validated = True
                        job.status = "no validator error"
                        job.validated_date = datetime.now(self.israel_tz)
                    continue
                # if (validator.url_is_company_page(job.link)): #fix for greenhouse company pages
                #     logger.info(f"Company page detected in: {job.link}")
                #     with commit_or_rollback(self.db, job):
                #         job.status = "company page"
                #         job.validated_date = datetime.now(self.israel_tz)
                #     continue
                if validator.uses_driver():
                    try:
                        shared_driver = driver_manager.get_or_create(validator)
                        validator.set_driver(shared_driver)
                    except Exception as e:
                        logger.error(f"🚫 Could not attach driver: {e}")
                        with commit_or_rollback(self.db, job):
                            job.validated = True
                            job.status = "driver error"
                            job.validated_date = datetime.now(self.israel_tz)
                        continue
                    
                if not self.validate_job(job, validator):
                    logger.warning(f"❌ Job validation failed: {job.link} id: {job.id} job.status: {job.status} error reason: {job.error_reason}")
                else:
                    logger.info(f"✅ Job validated: {job.link} id: {job.id}")
            return self.results

    def validate_job(self, job: JobPost, validator=None) -> bool:
        metadata = {}
        try:
            # validator = ValidatorFactory.create_validator(job.link)
            if not validator:
                logger.warning(f"⚠️ No validator for: {job.link}")
                with commit_or_rollback(self.db, job):
                    job.validated = True
                    job.status = "no validator error"
                    job.validated_date = datetime.now(self.israel_tz)
                return False

            if not validator.validate():
                logger.error(f"❌ Validation failed: {job.link} id: {job.id} reason: {validator.error_reason}")
                
                with commit_or_rollback(self.db, job):
                    job.validated = True
                    job.status = validator.job_status or "validation failed"
                    job.error_reason = validator.error_reason or "Validation failed"
                    job.validated_date = datetime.now(self.israel_tz)
                return False

            try:
                metadata = validator.extract_metadata()
                logger.debug(f"📦 Metadata: {metadata}")

                self.apply_metadata(job, metadata, [
                "title", "location", "company", 
                    "description", "posted_time", "requirements", "link", "responsibilities"
                ], validator)

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
            except LocationValidationError as e:
                logger.warning(f"⚠️ Validation error for job {job.link}: {e}")    
                with commit_or_rollback(self.db, job):
                    job.validated = True
                    job.status = "validation failed"
                    job.error_reason = str(e) or "job location is not in Israel"
                    job.validated_date = datetime.now(self.israel_tz)
                return False
        except Exception as e:
            logger.error(f"Error validating job {job.link}: {e}")
            logger.exception(validator.log_prefix(f"Error validating job {job.link}"))
            logger.warning(f"🚨 Skipping DB update due to unexpected exception — job will remain 'pending'")

            return False

    def run_batch(self, jobs: list[JobPost]):
        for job in jobs:
            self.validate_job(job)

    def apply_metadata(self,job: JobPost, metadata: dict, fields: list[str], validator=None):
        """ Apply metadata to the job object.
        Args:
            job (JobPost): The job object to update.
            metadata (dict): The metadata dictionary containing new values.
            fields (list[str]): List of fields to update in the job object.
        """
        metadata = {k: v for k, v in metadata.items() if k in fields and v is not None}
        logger.debug(f"metadata before pydantic: {metadata}")
        try:
            validated = JobPostUpdate(**metadata)
            logger.debug(f"metadata after pydantic JobPostUpdate validated var name: {validated}")

            updates = validated.model_dump(exclude_unset=True)
            logger.debug(f"Applying updates to keys {updates.keys()}")
            logger.debug(f"Updates to apply: {updates}")

            updated_fields = []
            
            for key, new_value  in updates.items():
                if key == "posted_time" and isinstance(new_value, str):
                    try:
                        new_value = datetime.strptime(new_value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                
                # ✅ Preserve original_link before overwriting link
                if key == "link" and getattr(job, key) != new_value:
                    if not getattr(job, "original_link", None):
                        job.original_link = getattr(job, "link")
                        logger.info(f"Preserving original_link: {job.original_link}")
                if hasattr(job, key):
                    if getattr(job, key) != new_value:
                        logger.info(f"Updating {key} from {getattr(job, key)} to {new_value}")
                        setattr(job, key, new_value)
                        updated_fields.append(key)
                else:
                    logger.warning(f"Key '{key}' not found in JobPost model. Skipping update for this field.")
            # Optional: track what was updated
            job.fields_updated = updated_fields
            job.last_validated_by = type(validator).__name__ if validator else "unknown"


        except ValidationError as e:
            logger.warning(f"⚠️ Skipping update for job {job.id} due to validation: {e}")
            job.status = "error"
            job.validation_notes = str(e)

        # for key in fields:
        #     if (
        #         hasattr(job, key) and 
        #         key in metadata and
        #         metadata[key] is not None
        #     ):
        #         current_value = getattr(job, key)
        #         new_value = metadata[key]
        #         if key == "posted_time":
        #             # Convert to datetime object if it's a string
        #             if isinstance(metadata[key], str):
        #                 try:
        #                     metadata[key] = datetime.strptime(metadata[key], "%Y-%m-%d %H:%M:%S")
        #                 except ValueError:
        #                     pass
        #         if current_value != new_value:
        #             logger.info(f"Updating {key} from {current_value} to {new_value}")
        #             # Update the job object with the new value
        #             setattr(job, key, metadata[key])



