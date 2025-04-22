import pytz 
from contextlib import contextmanager
from sqlalchemy.orm import Session
from app.models.job_post import JobPost
from app.log_config import logger
from datetime import datetime

ISRAEL_TZ = pytz.timezone("Israel")

@contextmanager
def commit_or_rollback(session: Session, job: JobPost):
    """
    Context manager to safely commit changes to a job post.
    Rolls back on failure and updates job status + validated_date if commit fails.
    """
    try:
        session.add(job)
        yield
        session.commit()
    except Exception as e:
        session.rollback()
        job.status = "commit_error"
        job.validated_date = datetime.now(ISRAEL_TZ)  # ⏰ Set timestamp inside commit context
        logger.exception(f"❌ Commit failed for {job.link}: {e}")
