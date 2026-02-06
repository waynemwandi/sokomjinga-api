# app/api/admin.py
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models

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
