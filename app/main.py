# import os
# from dotenv import load_dotenv
# load_dotenv()
# print("ENV FILE FOUND?", os.path.exists(".env"))
# print("DATABASE_URL =", os.getenv("DATABASE_URL"))
import os
from dotenv import load_dotenv
from openai import OpenAI
from app.config import settings
load_dotenv()
client = OpenAI(api_key=settings.openai_api_key)



from app.models.job_post import JobPost
from app.schemas.job_post_schema import JobPostUpdate, JobValidationResult
from app.utils.chrome_driver_manger import DriverManager
from app.utils.page_scraper import extract_visible_text_from_url
from app.validators.factory import ValidatorFactory
from fastapi import Query
import requests
from bs4 import BeautifulSoup

load_dotenv()
print("ENV FILE FOUND?", os.path.exists(".env"))
print("DEBUG =", os.getenv("DEBUG"))
from app.config import settings

print("🔎 settings.DEBUG =", settings.DEBUG)
print(f"🧪 DEBUGPY = {settings.DEBUGPY}")
print(f"🔁 Uvicorn --reload active? {'--reload' in os.getenv('UVICORN_RELOAD', '')}")
if settings.UVICORN_RELOAD:
    print("🧪 DEV mode: auto-reloading enabled")
else:
    print("🚀 PROD mode: running stable server")

from app.config import settings


from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.log_config import logger
from app.services.validation_service import JobValidatorService
from app.db.session import SessionLocal

os.getcwd()
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


@app.get("/extract_job/{job_url}")
def extract_job_data(job_html_or_text: str) -> dict:
    prompt = f"""
    Extract the following job fields from this text. Respond in valid JSON:
    - title
    - company
    - location
    - posted_date
    - description
    - requirements
    - seniority_level
    - employment_type
    -required expreience years
    - salary    
    - job_link

    Text:
    {job_html_or_text}
    """

    response = OpenAI.ChatCompletion.create(
        model="gpt-3.5-turbo",  # use gpt-3.5-turbo if you want cheaper
        messages=[
            {"role": "system", "content": "You extract structured job data from messy text or HTML."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
    )

    return response.choices[0].message.content  # This will be a JSON string

    return { "message": "Welcome to the Job Validator API!" }



###For testing only

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

@app.get("/extract-job-url")
def extract_job_data_from_url(url: str = Query(..., description="Job posting URL")):
    # Step 1: Fetch HTML
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching page: {e}")

    # Step 2: Parse and clean text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    clean_text = soup.get_text(separator="\n").strip()
    clean_text = clean_text[:4000]  # Limit size for GPT token limit

    # Step 3: Send to OpenAI
    prompt = f"""
    Extract the following job fields from this job post text. Return JSON:
    - title
    - company
    - location
    - posted_date
    - description
    - requirements
    - seniority_level
    - employment_type
    - required experience (years)
    - salary
    - job_link

    Job Text:
    {clean_text}
    """

    try:
        response = OpenAI.ChatCompletion.create(
            model="gpt-4o",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You extract structured job data from messy job post text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")
    
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
    
@app.post("/validate/{job_id}",response_model=JobValidationResult)
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
        return JobValidationResult(
            job_id=job.id,
            validated_by=type(validator).__name__,
            status=job.status,
            validated_date=job.validated_date.isoformat() if job.validated_date else None,
            update_success=result,
            fields_updated=job.fields_updated or [],
            notes=job.validation_notes,
            job_link=service.results[0].get('link') if service.results else job.link,
        )
    




@app.get("/extract-job-gpt-selenium")
def extract_job_gpt_with_driver(url: str):
    try:
        result = extract_visible_text_from_url(url)
        metadata = result["metadata"]
        visible_text = result["visible_text"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ChromeDriver error: {e}")

    prompt = f"""
    Extract the following job fields from this job post. Respond in JSON:
    - title
    - company
    - location
    - posted_date
    - description
    - requirements
    - seniority_level
    - employment_type
    - required experience (years)
    - salary
    - job_link

    Job Text:
    {visible_text}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You extract structured job data from text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
        )

        result = response.choices[0].message.content
        usage = response.usage

        # Optional cost estimation
        pricing = {"input": 0.0005, "output": 0.0015}
        cost_usd = (
            usage.prompt_tokens * pricing["input"] +
            usage.completion_tokens * pricing["output"]
        ) / 1000

        return {
            "metadata_from_page": metadata,
            "job_data_from_gpt": result,
            "tokens_used": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            },
            "estimated_cost_usd": round(cost_usd, 5)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")