# app/api/admin.py
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db  # you already use this in other routers
from app.db import models

router = APIRouter(prefix="/admin", tags=["admin"])


class StatsOut(BaseModel):
    total_users: int
    signups_last_7d: int
    logins_today: int
    logins_last_7d: int
    logins_by_provider: dict[str, int]


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
