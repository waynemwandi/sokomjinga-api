# app/api/wallet.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/wallet", tags=["wallet"])


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
