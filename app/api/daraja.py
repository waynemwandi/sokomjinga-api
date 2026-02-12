import base64
import datetime
import json

import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.wallet import get_or_create_mpesa_clearing_account
from app.core.config import get_settings
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/daraja", tags=["daraja"])

settings = get_settings()


# ---------------------------------------
# Access Token
# ---------------------------------------
def get_access_token():
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(
        url,
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
    )
    response.raise_for_status()
    return response.json()["access_token"]


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

    access_token = get_access_token()

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        (settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp).encode()
    ).decode()

    account_reference = f"MM-{deposit.id}"

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": deposit.amount_cents // 100,
        "PartyA": deposit.user.profile.phone_e164.replace("+", ""),
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": deposit.user.profile.phone_e164.replace("+", ""),
        "CallBackURL": f"{settings.MPESA_CALLBACK_BASE}/api/daraja/stk-callback",
        "AccountReference": account_reference,
        "TransactionDesc": "MM Wallet Topup",
    }

    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.post(
        f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers,
    )

    data = response.json()

    if data.get("ResponseCode") == "0":
        deposit.status = "stk_sent"
        deposit.checkout_request_id = data.get("CheckoutRequestID")
        deposit.merchant_request_id = data.get("MerchantRequestID")
        db.commit()
    else:
        deposit.status = "stk_failed"
        db.commit()

    return data


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
        pass

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

    event = models.MpesaEvent(
        event_type="c2b_confirmation",
        payload_json=json.dumps(payload),
        mpesa_trans_id=payload.get("TransID"),
    )
    db.add(event)
    db.commit()

    bill_ref = payload.get("BillRefNumber")

    if not bill_ref or not bill_ref.startswith("MM-"):
        return {"ResultCode": 0, "ResultDesc": "Ignored"}

    deposit_id = bill_ref.replace("MM-", "")

    deposit = db.query(models.WalletDeposit).filter_by(id=deposit_id).first()
    if not deposit or deposit.status == "confirmed":
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

    db.commit()

    return {"ResultCode": 0, "ResultDesc": "Accepted"}
