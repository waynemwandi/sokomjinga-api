# app/db/models.py
import uuid
from datetime import datetime

from requests import Session
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import INTEGER as MySQLInteger
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()

# Wallet currency constants
CENT_SCALE = 100  # 1 KES = 100 cents


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
    projected_end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class WalletAccount(TimestampMixin, Base):
    __tablename__ = "wallet_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)

    # Link to user for normal wallets; NULL for system accounts
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # "user_wallet", "mpesa_clearing", "platform_fee", "market_escrow", etc
    type: Mapped[str] = mapped_column(String(32), nullable=False)

    # "KES" for now
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")

    # "active", "frozen", "closed"
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )

    # Optional extra info, e.g. which market an escrow account belongs to
    meta_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", backref="wallet_accounts")


class WalletBalance(TimestampMixin, Base):
    __tablename__ = "wallet_balances"

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wallet_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # store in "cents"
    available_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")

    account: Mapped["WalletAccount"] = relationship("WalletAccount", backref="balance")


class WalletLedgerEntry(Base):
    __tablename__ = "wallet_ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    debit_account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wallet_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    credit_account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wallet_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")

    # High-level business meaning
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    # Link back to business objects
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    debit_account: Mapped["WalletAccount"] = relationship(
        "WalletAccount", foreign_keys=[debit_account_id]
    )
    credit_account: Mapped["WalletAccount"] = relationship(
        "WalletAccount", foreign_keys=[credit_account_id]
    )


class WalletDeposit(TimestampMixin, Base):
    __tablename__ = "wallet_deposits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wallet_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")

    # pending | stk_sent | stk_success | stk_failed | confirmed | failed
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
    )

    # C2B fields
    mpesa_reference: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    mpesa_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # STK fields
    checkout_request_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    merchant_request_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    user: Mapped["User"] = relationship("User", backref="wallet_deposits")
    account: Mapped["WalletAccount"] = relationship("WalletAccount", backref="deposits")


class WalletWithdrawal(TimestampMixin, Base):
    __tablename__ = "wallet_withdrawals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wallet_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")

    # "pending", "approved", "processing", "completed", "failed"
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )

    mpesa_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mpesa_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship("User", backref="wallet_withdrawals")
    account: Mapped["WalletAccount"] = relationship(
        "WalletAccount", backref="withdrawals"
    )


class WalletBet(TimestampMixin, Base):
    __tablename__ = "wallet_bets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    market_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    outcome_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("outcomes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # How much money we locked from the user's wallet for this bet (in wallet "cents")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # optional: how many "shares" the user bought
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # optional: price per share (1–100) at the moment of the bet (for now we can
    # just set something simple and improve later)
    price_cents_at_bet: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # "open" (market not resolved), "settled_won", "settled_lost", "cancelled"
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")

    # link back to the ledger entry that locked the funds
    ledger_entry_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("wallet_ledger_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user: Mapped["User"] = relationship("User", backref="wallet_bets")
    market: Mapped["Market"] = relationship("Market", backref="wallet_bets")
    outcome: Mapped["Outcome"] = relationship("Outcome", backref="wallet_bets")
    ledger_entry: Mapped["WalletLedgerEntry"] = relationship(
        "WalletLedgerEntry", backref="wallet_bets"
    )


class MarketPriceHistory(Base):
    __tablename__ = "market_price_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)

    market_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    outcome_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("outcomes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # snapshot of the outcome price at this time (0–100)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # total stake on this outcome in cents at this time
    total_stake_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    market: Mapped["Market"] = relationship("Market", backref="price_history")
    outcome: Mapped["Outcome"] = relationship("Outcome", backref="price_history")


class MpesaEvent(Base):
    __tablename__ = "mpesa_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # "stk_callback", "c2b_validation", "c2b_confirmation"

    mpesa_trans_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
