# app/config.py
import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv()  # Load before BaseSettings tries to access anything

from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn

class Settings(BaseSettings):
    DATABASE_URL: PostgresDsn
    CLIENT_ID: str = "job-validator"
    DEBUG: bool = Field(default=False)
    DEBUGPY: bool = Field(default=False)
    ISRAEL_TZ: str = "Asia/Jerusalem"
    # DEBUG FOR LOCAL ENVIRONMENT
    UVICORN_RELOAD: Optional[str] = Field(default=None, alias="UVICORN_RELOAD")

    class Config:
        env_file = ".env"


settings = Settings()
