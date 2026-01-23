# app/db/session.py

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,  # avoid stale connections
)

# NOTE: this is a *factory*, not a Session instance
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: create a new Session for each request
    and always close it afterwards.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
