# app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "SokoMjinga API"
    ENV: str = "dev"  # dev | staging | prod
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # TODO: Add DATABASE_URL here
    # DATABASE_URL: str = "mysql+pymysql://app:apppass@localhost:3306/sokomjinga"

    # CORS origins, comma-separated
    CORS_ORIGINS: str = ""


@lru_cache
def get_settings() -> Settings:
    # cached so we don’t reparse env repeatedly
    return Settings()
