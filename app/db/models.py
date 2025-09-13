import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


def _id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Market(TimestampMixin, Base):
    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    close_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    outcomes: Mapped[list["Outcome"]] = relationship(
        "Outcome", back_populates="market", cascade="all, delete-orphan"
    )


class Outcome(TimestampMixin, Base):
    __tablename__ = "outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    market_id: Mapped[str] = mapped_column(
        ForeignKey("markets.id"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g., "Yes", "No"
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0..100

    status: Mapped[str] = mapped_column(String(16), default="open")

    market: Mapped["Market"] = relationship(back_populates="outcomes")


# add to Market (inside class Market):
outcomes: Mapped[list["Outcome"]] = relationship(
    back_populates="market", cascade="all, delete-orphan"
)
