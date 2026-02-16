# app/api/wallet.py
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db import models
from app.db.session import get_db
from app.services.mpesa import trigger_stk_push

router = APIRouter(prefix="/wallet", tags=["wallet"])


class StatementItem(BaseModel):
    id: str
    created_at: datetime
    kind: str

    amount_cents: int
    signed_amount_cents: int
    currency: str
    direction: str  # "in" | "out"

    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None

    mpesa_reference: Optional[str] = None
    mpesa_phone: Optional[str] = None


class StatementResponse(BaseModel):
    items: List[StatementItem]
    total: int


class WalletSummary(BaseModel):
    balance_cents: int
    currency: str = "KES"


class CreateDepositRequest(BaseModel):
    # must be > 0
    amount_cents: int = Field(..., gt=0)


class DepositResponse(BaseModel):
    id: str
    status: str
    amount_cents: int
    currency: str


class ConfirmDepositRequest(BaseModel):
    mpesa_reference: str
    mpesa_phone: str | None = None


def get_or_create_user_wallet(db: Session, user: models.User) -> models.WalletAccount:
    # Try find existing wallet account
    acct = (
        db.query(models.WalletAccount)
        .filter(
            models.WalletAccount.user_id == user.id,
            models.WalletAccount.type == "user_wallet",
            models.WalletAccount.status == "active",
        )
        .first()
    )
    if acct:
        return acct

    # Create new wallet account + balance row
    acct = models.WalletAccount(
        user_id=user.id,
        type="user_wallet",
        currency="KES",
        status="active",
    )
    db.add(acct)
    db.flush()  # so acct.id is available

    bal = models.WalletBalance(
        account_id=acct.id,
        available_cents=0,
        pending_cents=0,
        currency="KES",
    )
    db.add(bal)
    db.flush()

    return acct


def get_or_create_mpesa_clearing_account(db: Session) -> models.WalletAccount:
    acct = (
        db.query(models.WalletAccount)
        .filter(
            models.WalletAccount.user_id.is_(None),
            models.WalletAccount.type == "mpesa_clearing",
        )
        .first()
    )
    if acct:
        return acct

    acct = models.WalletAccount(
        user_id=None,
        type="mpesa_clearing",
        currency="KES",
        status="active",
    )
    db.add(acct)
    db.flush()

    bal = models.WalletBalance(
        account_id=acct.id,
        available_cents=0,
        pending_cents=0,
        currency="KES",
    )
    db.add(bal)
    db.flush()

    return acct


def get_or_create_market_escrow_account(db: Session) -> models.WalletAccount:
    """
    System account that holds all locked stakes for open markets.

    - user_id is NULL (it's not tied to a user)
    - type = 'market_escrow'
    """
    acct = (
        db.query(models.WalletAccount)
        .filter(
            models.WalletAccount.user_id.is_(None),
            models.WalletAccount.type == "market_escrow",
        )
        .first()
    )
    if acct:
        return acct

    # Create account row
    acct = models.WalletAccount(
        user_id=None,
        type="market_escrow",
        currency="KES",
        status="active",
    )
    db.add(acct)
    db.flush()  # ensure acct.id is available

    # Create matching balance row
    bal = models.WalletBalance(
        account_id=acct.id,
        available_cents=0,
        pending_cents=0,
        currency="KES",
    )
    db.add(bal)
    db.flush()

    return acct


def get_or_create_platform_fee_account(db: Session) -> models.WalletAccount:
    """
    System account where your platform fees accumulate.

    - user_id is NULL
    - type = 'platform_fee'
    """
    acct = (
        db.query(models.WalletAccount)
        .filter(
            models.WalletAccount.user_id.is_(None),
            models.WalletAccount.type == "platform_fee",
        )
        .first()
    )
    if acct:
        return acct

    # Create account row
    acct = models.WalletAccount(
        user_id=None,
        type="platform_fee",
        currency="KES",
        status="active",
    )
    db.add(acct)
    db.flush()

    # Create matching balance row
    bal = models.WalletBalance(
        account_id=acct.id,
        available_cents=0,
        pending_cents=0,
        currency="KES",
    )
    db.add(bal)
    db.flush()

    return acct


@router.get("/me", response_model=WalletSummary)
def get_my_wallet(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    acct = get_or_create_user_wallet(db, current_user)
    bal = (
        db.query(models.WalletBalance)
        .filter(models.WalletBalance.account_id == acct.id)
        .first()
    )
    if not bal:
        raise HTTPException(status_code=500, detail="Wallet balance missing")

    return WalletSummary(balance_cents=bal.available_cents, currency=bal.currency)


@router.post(
    "/deposits",
    response_model=DepositResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_deposit(
    payload: CreateDepositRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    # Confirm phone is configured for STK push
    profile = db.get(models.UserProfile, current_user.id)

    if not profile or not profile.phone_e164:
        raise HTTPException(
            status_code=400,
            detail="Phone number not configured",
        )

    user_wallet = get_or_create_user_wallet(db, current_user)

    dep = models.WalletDeposit(
        user_id=current_user.id,
        account_id=user_wallet.id,
        amount_cents=payload.amount_cents,
        currency="KES",
        status="pending",
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)

    # Trigger STK push immediately after creating deposit

    trigger_stk_push(dep, db)

    db.refresh(dep)  # refresh to get updated status (stk_sent or stk_failed)

    return DepositResponse(
        id=dep.id,
        status=dep.status,
        amount_cents=dep.amount_cents,
        currency=dep.currency,
    )


@router.post("/deposits/{deposit_id}/confirm", response_model=DepositResponse)
def confirm_deposit_dev_only(
    deposit_id: str,
    payload: ConfirmDepositRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    DEV ONLY:
    Simulates a Daraja callback confirming a payment.
    Later we'll replace this with the real C2B/STK callback handler.
    """
    dep = (
        db.query(models.WalletDeposit)
        .filter(
            models.WalletDeposit.id == deposit_id,
            models.WalletDeposit.user_id == current_user.id,
        )
        .first()
    )
    if not dep:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if dep.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Deposit is already {dep.status}",
        )

    user_wallet = (
        db.query(models.WalletAccount)
        .filter(models.WalletAccount.id == dep.account_id)
        .with_for_update()
        .one()
    )
    mpesa_clearing = get_or_create_mpesa_clearing_account(db)

    # Lock balances
    user_bal = (
        db.query(models.WalletBalance)
        .filter(models.WalletBalance.account_id == user_wallet.id)
        .with_for_update()
        .one()
    )
    mpesa_bal = (
        db.query(models.WalletBalance)
        .filter(models.WalletBalance.account_id == mpesa_clearing.id)
        .with_for_update()
        .one()
    )

    # Create ledger entry
    entry = models.WalletLedgerEntry(
        debit_account_id=mpesa_clearing.id,
        credit_account_id=user_wallet.id,
        amount_cents=dep.amount_cents,
        currency=dep.currency,
        kind="deposit",
        reference_type="wallet_deposit",
        reference_id=dep.id,
        description="DEV deposit confirmation",
    )
    db.add(entry)

    # Update balances atomically
    mpesa_bal.available_cents -= dep.amount_cents
    user_bal.available_cents += dep.amount_cents

    # Update deposit
    dep.status = "confirmed"
    dep.mpesa_reference = payload.mpesa_reference
    dep.mpesa_phone = payload.mpesa_phone

    db.commit()
    db.refresh(dep)

    return DepositResponse(
        id=dep.id,
        status=dep.status,
        amount_cents=dep.amount_cents,
        currency=dep.currency,
    )


# Query/poll deposit status to inform frontend of stk status (pending, stk_sent, stk_failed, confirmed)
@router.get("/deposits/{deposit_id}", response_model=DepositResponse)
def get_deposit(
    deposit_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    dep = (
        db.query(models.WalletDeposit)
        .filter(
            models.WalletDeposit.id == deposit_id,
            models.WalletDeposit.user_id == current_user.id,
        )
        .first()
    )

    if not dep:
        raise HTTPException(status_code=404, detail="Deposit not found")

    return DepositResponse(
        id=dep.id,
        status=dep.status,
        amount_cents=dep.amount_cents,
        currency=dep.currency,
    )


@router.get("/statement", response_model=StatementResponse)
def get_wallet_statement(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    # Find active user wallet
    wallet = (
        db.query(models.WalletAccount)
        .filter(
            models.WalletAccount.user_id == current_user.id,
            models.WalletAccount.type == "user_wallet",
            models.WalletAccount.status == "active",
        )
        .first()
    )
    if not wallet:
        return StatementResponse(items=[], total=0)

    q = db.query(models.WalletLedgerEntry).filter(
        (models.WalletLedgerEntry.debit_account_id == wallet.id)
        | (models.WalletLedgerEntry.credit_account_id == wallet.id)
    )

    total = q.count()

    entries = (
        q.order_by(models.WalletLedgerEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    items: list[StatementItem] = []

    for entry in entries:
        is_in = entry.credit_account_id == wallet.id
        direction = "in" if is_in else "out"
        signed_amount = entry.amount_cents if is_in else -entry.amount_cents

        mpesa_reference = None
        mpesa_phone = None

        if entry.reference_type == "wallet_deposit" and entry.reference_id:
            dep = (
                db.query(models.WalletDeposit)
                .filter(models.WalletDeposit.id == entry.reference_id)
                .first()
            )
            if dep:
                mpesa_reference = dep.mpesa_reference
                mpesa_phone = dep.mpesa_phone

        items.append(
            StatementItem(
                id=entry.id,
                created_at=entry.created_at,
                kind=entry.kind,
                amount_cents=entry.amount_cents,
                signed_amount_cents=signed_amount,
                currency=entry.currency,
                direction=direction,
                reference_type=entry.reference_type,
                reference_id=entry.reference_id,
                description=entry.description,
                mpesa_reference=mpesa_reference,
                mpesa_phone=mpesa_phone,
            )
        )

    return StatementResponse(items=items, total=total)
