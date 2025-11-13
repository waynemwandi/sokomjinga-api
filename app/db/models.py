# app/db/models.py
import uuid
from datetime import datetime

from requests import Session
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


def _id() -> str:
    return str(uuid.uuid4())


def log_auth_event(db: Session, user_id: str, event_type: str, provider: str):
    e = AuthEvent(user_id=user_id, event_type=event_type, provider=provider)
    db.add(e)


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


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    # 1-to-1 via unique FK
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    # Store phone in E.164 format: e.g. +2547XXXXXXXX (nullable until first top-up)
    phone_e164: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )

    # Verification + KYC fields
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    kyc_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped[User] = relationship("User", back_populates="profile")
    # auth metadata
    auth_provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="password",
        server_default=text("'password'"),
    )
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "signup" or "login"
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "password" or "google"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")
