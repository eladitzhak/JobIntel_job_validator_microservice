from sqlalchemy.orm import Session
from datetime import datetime
import pytz
from pydantic import ValidationError


from app.schemas.job_post_schema import JobPostUpdate
from app.models.job_post import JobPost
from app.db.session import SessionLocal
from app.validators.factory import ValidatorFactory
from app.config import settings
from app.log_config import logger  
from app.utils.db_utils import commit_or_rollback
from app.utils.chrome_driver_manger import DriverManager
#TODO:INJECT DEPENDS(get_db)?
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
        
        with DriverManager() as driver_manager:
            for job in pending_jobs:
                logger.info(f"🔍 Validating: {job.link} id: {job.id}")
                
                try:
                    validator = ValidatorFactory.create_validator(job.link)
                except Exception as e:
                    logger.warning(f"❌ No validator implemented for: {job.link}")
                    with commit_or_rollback(self.db, job):
                        job.status = "no validator"
                        job.validated_date = datetime.now(self.israel_tz)
                    continue
                if not validator:
                    logger.warning(f"⚠️ No validator for: {job.link}")
                    with commit_or_rollback(self.db, job):
                        job.status = "no validator error"
                        job.validated_date = datetime.now(self.israel_tz)
                    continue
                if validator.uses_driver():
                    try:
                        shared_driver = driver_manager.get_or_create(validator)
                        validator.set_driver(shared_driver)
                    except Exception as e:
                        logger.error(f"🚫 Could not attach driver: {e}")
                        with commit_or_rollback(self.db, job):
                            job.status = "driver error"
                            job.validated_date = datetime.now(self.israel_tz)
                        continue

                    if not self.validate_job(job, validator):
                        logger.warning(f"❌ Job validation failed: {job.link}")
                    else:
                        logger.info(f"✅ Job validated: {job.link}")
            return self.results

###version 1 of driver pool
        # try:
        #     for job in pending_jobs:
        #         logger.info(f"🔍 Validating: {job.link} id: {job.id}")
                
        #         validator = ValidatorFactory.create_validator(job.link)

        #         if validator and validator.uses_driver():
        #             validator_type = type(validator).__name__.lower()
        #             if validator_type not in driver_pool:
        #                 driver_pool[validator_type] = validator._init_driver()
        #                 logger.info(f"🚗 Created shared driver for {validator_type}")

        #             validator.set_driver(driver_pool[validator_type])

        #         if self.validate_job(job, validator):
        #             logger.info(f"✅ Job validated: {job.link} id: {job.id}")
        #         else: 
        #             logger.error(f"❌ Job validation failed: {job.link} id: {job.id}")
        # except Exception as e:
        #     logger.error(f"An error occurred during job validation: {e}")
        # finally:
        #     for driver in driver_pool.values():
        #         try:
        #             driver.quit()
        #         except Exception:
        #             logger.warning("⚠️ Failed to quit one of the shared drivers")
    
    # def validate_job(self, job: JobPost) -> bool:
    def validate_job(self, job: JobPost, validator=None) -> bool:
        metadata = {}
        try:
            # validator = ValidatorFactory.create_validator(job.link)
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
            # self.apply_metadata(job, metadata, [
            #         "title", "location", "company", 
            #         "description", "posted_time", "requirements"
            # ])
            self.apply_metadata(job, metadata, [
                "title", "location", "company", 
                "description", "posted_time", "requirements"
            ], validator)
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
            logger.debug(f"Applying updates to keys {updates.keys()}: {updates}")

            updated_fields = []
            
            for key, new_value  in updates.items():
                if key == "posted_time" and isinstance(new_value, str):
                    try:
                        new_value = datetime.strptime(new_value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                if hasattr(job, key) and getattr(job, key) != new_value:
                    logger.info(f"Updating {key} from {getattr(job, key)} to {new_value}")
                    setattr(job, key, new_value)
                    updated_fields.append(key)
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



