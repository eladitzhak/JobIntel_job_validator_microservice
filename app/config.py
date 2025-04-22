# app/config.py
import os
from dotenv import load_dotenv
load_dotenv()  # Load before BaseSettings tries to access anything

from pydantic_settings import BaseSettings
from pydantic import PostgresDsn

class Settings(BaseSettings):
    DATABASE_URL: PostgresDsn
    CLIENT_ID: str = "job-validator"
    DEBUG: bool = True
    ISRAEL_TZ: str = "Asia/Jerusalem"

    class Config:
        env_file = ".env"


settings = Settings()
