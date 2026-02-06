# app/api/admin.py
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.api.deps import get_db, require_admin
from app.db import models
from app.db.models import WalletAccount

router = APIRouter(prefix="/admin", tags=["admin"])


class StatsOut(BaseModel):
    total_users: int
    signups_last_7d: int
    logins_today: int
    logins_last_7d: int
    logins_by_provider: dict[str, int]


class AuthDayOut(BaseModel):
    date: date
    logins: int


class AuthTimeseriesOut(BaseModel):
    days: int
    points: list[AuthDayOut]


@router.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    today_start = datetime(now.year, now.month, now.day)

    total_users = db.query(models.User).count()

    signups_last_7d = (
        db.query(models.AuthEvent)
        .filter(
            models.AuthEvent.event_type == "signup",
            models.AuthEvent.created_at >= seven_days_ago,
        )
        .count()
    )

    logins_today = (
        db.query(models.AuthEvent)
        .filter(
            models.AuthEvent.event_type == "login",
            models.AuthEvent.created_at >= today_start,
        )
        .count()
    )

    logins_last_7d = (
        db.query(models.AuthEvent)
        .filter(
            models.AuthEvent.event_type == "login",
            models.AuthEvent.created_at >= seven_days_ago,
        )
        .count()
    )

    provider_rows = (
        db.query(models.AuthEvent.provider, func.count(models.AuthEvent.id))
        .filter(models.AuthEvent.event_type == "login")
        .group_by(models.AuthEvent.provider)
        .all()
    )
    logins_by_provider = {provider: count for provider, count in provider_rows}

    return StatsOut(
        total_users=total_users,
        signups_last_7d=signups_last_7d,
        logins_today=logins_today,
        logins_last_7d=logins_last_7d,
        logins_by_provider=logins_by_provider,
    )


@router.get("/auth/timeseries", response_model=AuthTimeseriesOut)
def auth_timeseries(
    days: int = 14,
    db: Session = Depends(get_db),
):
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days - 1)

    rows = (
        db.query(
            func.date(models.AuthEvent.created_at).label("day"),
            func.count(models.AuthEvent.id).label("count"),
        )
        .filter(
            models.AuthEvent.event_type == "login",
            models.AuthEvent.created_at >= start_date,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    # Convert DB rows to a dict for easy lookup
    counts_by_day = {row.day: row.count for row in rows}

    points: list[AuthDayOut] = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        points.append(
            AuthDayOut(
                date=d,
                logins=counts_by_day.get(d, 0),
            )
        )

    return AuthTimeseriesOut(days=days, points=points)


@router.get("/wallets/summary")
def wallet_summary(db: Session = Depends(get_db)):
    totals = (
        db.query(
            func.count(models.WalletAccount.id),
            func.sum(models.WalletBalance.available_cents),
            func.sum(models.WalletBalance.pending_cents),
        )
        .join(
            models.WalletBalance,
            models.WalletBalance.account_id == models.WalletAccount.id,
        )
        .one()
    )

    user_wallets = (
        db.query(func.count(models.WalletAccount.id))
        .filter(models.WalletAccount.user_id.isnot(None))
        .scalar()
    )

    system_wallets = (
        db.query(func.count(models.WalletAccount.id))
        .filter(models.WalletAccount.user_id.is_(None))
        .scalar()
    )

    return {
        "total_wallets": totals[0] or 0,
        "user_wallets": user_wallets or 0,
        "system_wallets": system_wallets or 0,
        "total_available_cents": totals[1] or 0,
        "total_pending_cents": totals[2] or 0,
        "currency": "KES",
    }


@router.get("/wallets/by-type")
def wallets_by_type(db: Session = Depends(get_db)):
    rows = (
        db.query(
            models.WalletAccount.type,
            func.count(models.WalletAccount.id),
            func.sum(models.WalletBalance.available_cents),
            func.sum(models.WalletBalance.pending_cents),
        )
        .join(
            models.WalletBalance,
            models.WalletBalance.account_id == models.WalletAccount.id,
        )
        .group_by(models.WalletAccount.type)
        .all()
    )

    return [
        {
            "type": r[0],
            "count": r[1],
            "available_cents": r[2] or 0,
            "pending_cents": r[3] or 0,
        }
        for r in rows
    ]


@router.get("/wallets/activity")
def wallet_activity(limit: int = 50, db: Session = Depends(get_db)):
    entries = (
        db.query(models.WalletLedgerEntry)
        .order_by(models.WalletLedgerEntry.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": e.id,
            "created_at": e.created_at,
            "kind": e.kind,
            "amount_cents": e.amount_cents,
            "debit_account_type": e.debit_account.type,
            "credit_account_type": e.credit_account.type,
            "reference_type": e.reference_type,
        }
        for e in entries
    ]


@router.get("/wallets")
def list_wallets(
    db: Session = Depends(get_db),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = (
        db.query(
            models.WalletAccount.id,
            models.WalletAccount.type,
            models.WalletAccount.user_id,
            models.WalletAccount.created_at,
            models.WalletAccount.updated_at,
            models.WalletBalance.available_cents,
            models.WalletBalance.pending_cents,
        )
        .join(
            models.WalletBalance,
            models.WalletBalance.account_id == models.WalletAccount.id,
        )
        .order_by(models.WalletAccount.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    total = db.query(func.count(models.WalletAccount.id)).scalar()

    return {
        "items": [
            {
                "id": r.id,
                "type": r.type,
                "user_id": r.user_id,
                "available_cents": r.available_cents or 0,
                "pending_cents": r.pending_cents or 0,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
