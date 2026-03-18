# app/core/config.py
from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "SokoMjinga API"
    ENV: str = "dev"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS origins, comma-separated
    CORS_ORIGINS: str = ""

    # DB pieces (defaults silence editor warnings; real values come from .env)
    DB_TYPE: str = ""
    DB_DRIVER: str = ""
    DB_HOST: str = ""
    DB_PORT: int = 3306
    DB_USER: str = ""
    DB_PASS: str = ""
    DB_NAME: str = ""

    # JWT / token settings (needed by security.py)
    SECRET_KEY: str = "changeme"
    JWT_ALG: str = "HS256"
    ACCESS_EXPIRE_MIN: int = 60
    REFRESH_EXPIRE_DAYS: int = 30

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""  # e.g. http://127.0.0.1:8000/auth/google/callback
    BASE_FRONTEND_URL: str = ""  # e.g. http://127.0.0.1:5173

    # Safaricom
    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_SHORTCODE: str = ""
    MPESA_PASSKEY: str = ""
    MPESA_BASE_URL: str = ""  # https://api.safaricom.co.ke
    MPESA_CALLBACK_BASE: str = ""  # https://maonimarket.com

    # Email Configuration
    SES_SMTP_HOST: str = ""
    SES_SMTP_PORT: int = 587
    SES_SMTP_USER: str = ""
    SES_SMTP_PASS: str = ""
    EMAIL_FROM: str = ""

    @computed_field(return_type=str)
    @property
    def database_url(self) -> str:
        return f"{self.DB_TYPE}+{self.DB_DRIVER}://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
