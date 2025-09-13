from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = scoped_session(
    sessionmaker(bind=engine, autocommit=False, autoflush=False)
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
