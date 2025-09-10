# app/core/config.py
from functools import lru_cache
from typing import List, Union

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "SokoMjinga API"
    ENV: str = "dev"  # dev | staging | prod
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # TODO: Add DATABASE_URL here
    # DATABASE_URL: str = "mysql+pymysql://app:apppass@localhost:3306/sokomjinga"

    CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_csv(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    # cached so we don’t reparse env repeatedly
    return Settings()
