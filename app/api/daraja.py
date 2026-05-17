# app/api/daraja.py
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.wallet import get_or_create_mpesa_clearing_account
from app.db import models
from app.db.session import get_db
from app.services.mpesa import trigger_stk_push

logger = logging.getLogger("maoni.daraja")

router = APIRouter(prefix="/daraja", tags=["daraja"])


# ---------------------------------------
# STK Push
# ---------------------------------------
@router.post("/stk-push/{deposit_id}")
def stk_push(deposit_id: str, db: Session = Depends(get_db)):

    deposit = db.query(models.WalletDeposit).filter_by(id=deposit_id).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit.status != "pending":
        raise HTTPException(status_code=400, detail="Deposit already processed")

    return trigger_stk_push(deposit, db)


# ---------------------------------------
# STK Callback
# ---------------------------------------
@router.post("/stk-callback")
def stk_callback(payload: dict, db: Session = Depends(get_db)):

    event = models.MpesaEvent(
        event_type="stk_callback",
        payload_json=json.dumps(payload),
    )
    db.add(event)
    db.commit()

    try:
        body = payload["Body"]["stkCallback"]
        checkout_id = body["CheckoutRequestID"]
        result_code = body["ResultCode"]

        deposit = (
            db.query(models.WalletDeposit)
            .filter_by(checkout_request_id=checkout_id)
            .first()
        )

        if deposit and result_code == 0:
            deposit.status = "stk_success"
        elif deposit:
            deposit.status = "stk_failed"

        db.commit()

    except Exception:
        logger.exception("STK callback processing failed")

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ---------------------------------------
# C2B Validation
# ---------------------------------------
@router.post("/c2b/validation")
def c2b_validation(payload: dict, db: Session = Depends(get_db)):

    event = models.MpesaEvent(
        event_type="c2b_validation",
        payload_json=json.dumps(payload),
    )
    db.add(event)
    db.commit()

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ---------------------------------------
# C2B Confirmation (Authoritative)
# ---------------------------------------
@router.post("/c2b/confirmation")
def c2b_confirmation(payload: dict, db: Session = Depends(get_db)):

    try:
        event = models.MpesaEvent(
            event_type="c2b_confirmation",
            payload_json=json.dumps(payload),
            mpesa_trans_id=payload.get("TransID"),
        )
        db.add(event)

        bill_ref = payload.get("BillRefNumber")
        print("CONFIRMATION received")
        print("BillRefNumber raw:", repr(bill_ref))

        if not bill_ref or not bill_ref.startswith("MM-"):
            db.commit()
            return {"ResultCode": 0, "ResultDesc": "Ignored"}

        deposit_id = bill_ref[3:]

        print("Extracted deposit_id:", repr(deposit_id), "length:", len(deposit_id))

        deposit = db.query(models.WalletDeposit).filter_by(id=deposit_id).first()
        print("Deposit lookup result:", deposit)
        if deposit:
            print("Deposit status before confirmation:", deposit.status)

        if not deposit:
            print("Deposit NOT FOUND")
            db.commit()
            return {"ResultCode": 0, "ResultDesc": "Deposit not found"}

        if deposit.status == "confirmed":
            print("Deposit already confirmed")
            db.commit()
            return {"ResultCode": 0, "ResultDesc": "Already processed"}

        user_wallet = deposit.account
        mpesa_clearing = get_or_create_mpesa_clearing_account(db)

        user_bal = (
            db.query(models.WalletBalance)
            .filter_by(account_id=user_wallet.id)
            .with_for_update()
            .one()
        )
        mpesa_bal = (
            db.query(models.WalletBalance)
            .filter_by(account_id=mpesa_clearing.id)
            .with_for_update()
            .one()
        )

        entry = models.WalletLedgerEntry(
            debit_account_id=mpesa_clearing.id,
            credit_account_id=user_wallet.id,
            amount_cents=deposit.amount_cents,
            currency=deposit.currency,
            kind="deposit",
            reference_type="wallet_deposit",
            reference_id=deposit.id,
            description="MPESA deposit",
        )

        db.add(entry)

        mpesa_bal.available_cents -= deposit.amount_cents
        user_bal.available_cents += deposit.amount_cents

        deposit.status = "confirmed"
        deposit.mpesa_reference = payload.get("TransID")
        deposit.mpesa_phone = payload.get("MSISDN")

        print("About to commit confirmation for deposit:", deposit.id)
        print("Setting mpesa_reference:", payload.get("TransID"))
        print("Setting mpesa_phone:", payload.get("MSISDN"))
        db.commit()

        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    except Exception as e:
        db.rollback()
        print("CONFIRMATION FAILED:", str(e))
        raise
