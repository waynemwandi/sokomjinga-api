# app/core/config.py
from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "SokoMjinga API"
    ENV: str = "dev"  # dev | staging | prod
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS origins, comma-separated
    CORS_ORIGINS: str = ""

    # DB pieces for SQLAlchemy URL
    DB_TYPE: str
    DB_DRIVER: str
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    @computed_field(return_type=str)
    @property
    def database_url(self) -> str:
        # Compose URL from the pieces (no secrets hard-coded)
        return f"{self.DB_TYPE}+{self.DB_DRIVER}://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings() -> Settings:
    # cached so we don’t reparse env repeatedly
    return Settings()
