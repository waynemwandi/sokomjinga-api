# app/api/admin.py
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.api.deps import get_db, require_admin
from app.db import models
from app.db.models import WalletAccount
from app.api.wallet import get_or_create_mpesa_clearing_account
from app.services.notifications import (
    send_withdrawal_completed,
    send_withdrawal_rejected,
)

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


class AdminUserOut(BaseModel):
    id: str
    email: str
    name: str | None
    is_active: bool
    is_admin: bool
    auth_provider: str | None
    created_at: datetime
    last_login_at: datetime | None
    wallet_accounts: int
    bets: int
    deposits: int


class AdminUsersOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class UserStatusIn(BaseModel):
    is_active: bool


class AdminWithdrawalOut(BaseModel):
    id: str
    user_id: str
    email: str
    name: str | None
    amount_cents: int
    currency: str
    status: str
    mpesa_phone: str | None
    mpesa_reference: str | None
    reason: str | None
    created_at: datetime
    updated_at: datetime


class AdminWithdrawalsOut(BaseModel):
    items: list[AdminWithdrawalOut]
    total: int
    limit: int
    offset: int


class WithdrawalStatusIn(BaseModel):
    status: str
    mpesa_reference: str | None = None
    reason: str | None = None


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


@router.get("/users", response_model=AdminUsersOut)
def list_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None),
):
    wallet_count = (
        db.query(
            models.WalletAccount.user_id.label("user_id"),
            func.count(models.WalletAccount.id).label("wallet_accounts"),
        )
        .filter(models.WalletAccount.user_id.isnot(None))
        .group_by(models.WalletAccount.user_id)
        .subquery()
    )

    bet_count = (
        db.query(
            models.WalletBet.user_id.label("user_id"),
            func.count(models.WalletBet.id).label("bets"),
        )
        .group_by(models.WalletBet.user_id)
        .subquery()
    )

    deposit_count = (
        db.query(
            models.WalletDeposit.user_id.label("user_id"),
            func.count(models.WalletDeposit.id).label("deposits"),
        )
        .group_by(models.WalletDeposit.user_id)
        .subquery()
    )

    last_login = (
        db.query(
            models.AuthEvent.user_id.label("user_id"),
            func.max(models.AuthEvent.created_at).label("last_login_at"),
        )
        .filter(models.AuthEvent.event_type == "login")
        .group_by(models.AuthEvent.user_id)
        .subquery()
    )

    query = (
        db.query(
            models.User.id,
            models.User.email,
            models.User.name,
            models.User.is_active,
            models.User.is_admin,
            models.User.created_at,
            models.UserProfile.auth_provider,
            last_login.c.last_login_at,
            func.coalesce(wallet_count.c.wallet_accounts, 0).label("wallet_accounts"),
            func.coalesce(bet_count.c.bets, 0).label("bets"),
            func.coalesce(deposit_count.c.deposits, 0).label("deposits"),
        )
        .outerjoin(models.UserProfile, models.UserProfile.user_id == models.User.id)
        .outerjoin(wallet_count, wallet_count.c.user_id == models.User.id)
        .outerjoin(bet_count, bet_count.c.user_id == models.User.id)
        .outerjoin(deposit_count, deposit_count.c.user_id == models.User.id)
        .outerjoin(last_login, last_login.c.user_id == models.User.id)
    )

    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            func.lower(models.User.email).like(needle)
            | func.lower(func.coalesce(models.User.name, "")).like(needle)
        )

    total = query.count()
    rows = (
        query.order_by(models.User.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return AdminUsersOut(
        items=[
            AdminUserOut(
                id=row.id,
                email=row.email,
                name=row.name,
                is_active=row.is_active,
                is_admin=row.is_admin,
                auth_provider=row.auth_provider,
                created_at=row.created_at,
                last_login_at=row.last_login_at,
                wallet_accounts=row.wallet_accounts or 0,
                bets=row.bets or 0,
                deposits=row.deposits or 0,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
def update_user_status(
    user_id: str,
    payload: UserStatusIn,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_admin and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin accounts cannot be deactivated from the dashboard",
        )

    user.is_active = payload.is_active
    db.commit()

    profile = (
        db.query(models.UserProfile)
        .filter(models.UserProfile.user_id == user.id)
        .one_or_none()
    )
    last_login_at = (
        db.query(func.max(models.AuthEvent.created_at))
        .filter(
            models.AuthEvent.user_id == user.id,
            models.AuthEvent.event_type == "login",
        )
        .scalar()
    )
    wallet_accounts = (
        db.query(func.count(models.WalletAccount.id))
        .filter(models.WalletAccount.user_id == user.id)
        .scalar()
        or 0
    )
    bets = (
        db.query(func.count(models.WalletBet.id))
        .filter(models.WalletBet.user_id == user.id)
        .scalar()
        or 0
    )
    deposits = (
        db.query(func.count(models.WalletDeposit.id))
        .filter(models.WalletDeposit.user_id == user.id)
        .scalar()
        or 0
    )

    return AdminUserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        is_admin=user.is_admin,
        auth_provider=profile.auth_provider if profile else None,
        created_at=user.created_at,
        last_login_at=last_login_at,
        wallet_accounts=wallet_accounts,
        bets=bets,
        deposits=deposits,
    )


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


def _admin_withdrawal_out(row) -> AdminWithdrawalOut:
    withdrawal, user = row
    return AdminWithdrawalOut(
        id=withdrawal.id,
        user_id=withdrawal.user_id,
        email=user.email,
        name=user.name,
        amount_cents=withdrawal.amount_cents,
        currency=withdrawal.currency,
        status=withdrawal.status,
        mpesa_phone=withdrawal.mpesa_phone,
        mpesa_reference=withdrawal.mpesa_reference,
        reason=withdrawal.reason,
        created_at=withdrawal.created_at,
        updated_at=withdrawal.updated_at,
    )


@router.get("/withdrawals", response_model=AdminWithdrawalsOut)
def list_withdrawals(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = (
        db.query(models.WalletWithdrawal, models.User)
        .join(models.User, models.User.id == models.WalletWithdrawal.user_id)
    )

    if status_filter and status_filter != "all":
        query = query.filter(models.WalletWithdrawal.status == status_filter)

    total = query.count()
    rows = (
        query.order_by(models.WalletWithdrawal.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return AdminWithdrawalsOut(
        items=[_admin_withdrawal_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/withdrawals/{withdrawal_id}", response_model=AdminWithdrawalOut)
def update_withdrawal_status(
    withdrawal_id: str,
    payload: WithdrawalStatusIn,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    next_status = payload.status.strip().lower()
    if next_status not in {"processing", "completed", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid withdrawal status",
        )

    withdrawal = (
        db.query(models.WalletWithdrawal)
        .filter(models.WalletWithdrawal.id == withdrawal_id)
        .with_for_update()
        .one_or_none()
    )
    if not withdrawal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Withdrawal not found",
        )

    if withdrawal.status in {"completed", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Withdrawal is already {withdrawal.status}",
        )

    user_wallet = (
        db.query(models.WalletAccount)
        .filter(models.WalletAccount.id == withdrawal.account_id)
        .with_for_update()
        .one()
    )
    user_balance = (
        db.query(models.WalletBalance)
        .filter(models.WalletBalance.account_id == user_wallet.id)
        .with_for_update()
        .one()
    )

    if next_status == "processing":
        withdrawal.status = "processing"
        db.commit()
    elif next_status == "failed":
        reason = (payload.reason or "").strip()
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reason is required when rejecting a withdrawal",
            )

        if user_balance.pending_cents < withdrawal.amount_cents:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Wallet pending balance is lower than withdrawal amount",
            )

        withdrawal.status = "failed"
        withdrawal.reason = reason
        user_balance.pending_cents -= withdrawal.amount_cents
        user_balance.available_cents += withdrawal.amount_cents
        db.commit()

        try:
            send_withdrawal_rejected(withdrawal.user, withdrawal)
        except Exception:
            pass
    else:
        reference = (payload.mpesa_reference or "").strip()
        if not reference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="M-Pesa reference is required when sending a withdrawal",
            )

        mpesa_clearing = get_or_create_mpesa_clearing_account(db)
        mpesa_balance = (
            db.query(models.WalletBalance)
            .filter(models.WalletBalance.account_id == mpesa_clearing.id)
            .with_for_update()
            .one()
        )

        if user_balance.pending_cents < withdrawal.amount_cents:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Wallet pending balance is lower than withdrawal amount",
            )

        entry = models.WalletLedgerEntry(
            debit_account_id=user_wallet.id,
            credit_account_id=mpesa_clearing.id,
            amount_cents=withdrawal.amount_cents,
            currency=withdrawal.currency,
            kind="withdrawal",
            reference_type="wallet_withdrawal",
            reference_id=withdrawal.id,
            description="Manual withdrawal sent",
        )
        db.add(entry)
        withdrawal.status = "completed"
        withdrawal.mpesa_reference = reference
        user_balance.pending_cents -= withdrawal.amount_cents
        mpesa_balance.available_cents += withdrawal.amount_cents
        db.commit()

        try:
            send_withdrawal_completed(withdrawal.user, withdrawal)
        except Exception:
            pass

    row = (
        db.query(models.WalletWithdrawal, models.User)
        .join(models.User, models.User.id == models.WalletWithdrawal.user_id)
        .filter(models.WalletWithdrawal.id == withdrawal_id)
        .one()
    )
    return _admin_withdrawal_out(row)
