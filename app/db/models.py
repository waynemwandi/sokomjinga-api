# app/db/models.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()


def _id() -> str:
    return str(uuid.uuid4())


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
