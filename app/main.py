# import os
# from dotenv import load_dotenv
# load_dotenv()
# print("ENV FILE FOUND?", os.path.exists(".env"))
# print("DATABASE_URL =", os.getenv("DATABASE_URL"))
import os
from dotenv import load_dotenv

from app.models.job_post import JobPost
from app.utils.chrome_driver_manger import DriverManager

from app.validators.factory import ValidatorFactory
load_dotenv()
print("ENV FILE FOUND?", os.path.exists(".env"))
print("DEBUG =", os.getenv("DEBUG"))
from app.config import settings

print("🔎 settings.DEBUG =", settings.DEBUG)

from app.config import settings


from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.log_config import logger
from app.services.validation_service import JobValidatorService
from app.db.session import SessionLocal


print("🔎 settinssgs.DEBUG =", settings.DEBUG)

if os.getenv("DEBUGPY", "false").lower() == "true":
    try:
        import debugpy
        print("🪲 debugpy imported!")
        debugpy.listen(("0.0.0.0", 5678))

        if not debugpy.is_client_connected():
            print("🛑 Waiting for debugger... (non-blocking)")
            import threading
            threading.Thread(target=debugpy.wait_for_client, daemon=True).start()
        else:
            print("✅ Debugger already attached.")
    except Exception as e:
        print(f"❌ debugpy failed: {e}")

app = FastAPI()

@app.get("/")
def read_root():
    return { "message": "Welcome to the Job Validator API!" }


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
        row = result.fetchone()
        return {
            "status": "ok",
            "db": "connected",
            "result": dict(row._mapping) if row else "No rows"
        }

    except Exception as e:
        logger.exception("❌ DB connection failed")
        return {"status": "error", "db": "not connected", "error": str(e)}


@app.post("/validate-pending")
def validate():
    service = JobValidatorService(None)  # Or pass DB session if you have one
    results = service.validate_pending_jobs()
    return {"results": results}
    
@app.post("/validate/{job_id}")
def validate_specific_job(job_id: int, db: Session = Depends(get_db)):
    # Step 1: Load job from DB
    job = db.query(JobPost).filter(JobPost.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Step 2: Create validator for the job's link
    validator = ValidatorFactory.create_validator(job.link)
    if not validator:
        raise HTTPException(status_code=400, detail="No validator available for this job")

    # Step 3: Initialize service
    service = JobValidatorService(db)

    # Step 4: Use ChromeDriver if needed
    with DriverManager() as driver_manager:
        if validator.uses_driver():
            try:
                shared_driver = driver_manager.get_or_create(validator)
                validator.set_driver(shared_driver)
            except Exception as e:
                logger.error(f"🚫 Could not attach driver: {e}")
                raise HTTPException(status_code=500, detail="Driver error")
                
        result = service.validate_job(job, validator)

    # Step 5: Return result
    return {
        "job_id": job.id,
        "validated_by": type(validator).__name__,
        "status": job.status,
        "validated_date": job.validated_date.isoformat() if job.validated_date else None,
        "update_success": result,
        "fields_updated": job.fields_updated,
        "notes": job.validation_notes,
        "job_link": service.results[0].get('link') or job.link,
    }