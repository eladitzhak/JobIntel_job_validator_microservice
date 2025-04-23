# import os
# from dotenv import load_dotenv
# load_dotenv()
# print("ENV FILE FOUND?", os.path.exists(".env"))
# print("DATABASE_URL =", os.getenv("DATABASE_URL"))
from app.config import settings


from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.log_config import logger
from app.services.validation_service import JobValidatorService
from app.db.session import SessionLocal


app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}


###For testing only

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

@app.get("/health/db")
def db_health_check(db: Session = Depends(get_db)):
    try:
        can_update = db.execute(text(
    "SELECT has_column_privilege('job_validator_user', 'job_posts', 'status')"
)).scalar()
    except Exception as update_err:
        logger.warning(f"⚠️ UPDATE permission check failed: {update_err}")
        can_update = False

    return {
        "status": "ok",
        "can_update_status_column": can_update
    }


@app.get("/health/db/basic")
def db_health_check_basic(db: Session = Depends(get_db)):
    try:
        # Just a simple query to check DB connection
        # result = db.execute(text("SELECT 1"))
        result = db.execute(text("SELECT * from JOB_POSTS limit 1"))

        return {"status": "ok", "db": "connected","result": result}
    except Exception as e:
        logger.exception("❌ DB connection failed")
        return {"status": "error", "db": "not connected", "error": str(e)}


@app.post("/validate-pending")
def validate():
    service = JobValidatorService(None)  # Or pass DB session if you have one
    results = service.validate_pending_jobs()
    return {"results": results}