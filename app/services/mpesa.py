# app/services/mpesa.py
import base64
import datetime

import requests
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models

settings = get_settings()


def get_access_token():
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(
        url,
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
    )
    response.raise_for_status()
    return response.json()["access_token"]


def trigger_stk_push(deposit: models.WalletDeposit, db: Session):
    # Guard against missing phone number
    if (
        not deposit.user
        or not deposit.user.profile
        or not deposit.user.profile.phone_e164
    ):
        deposit.status = "stk_failed"
        db.commit()
        return {"error": "Phone number missing"}

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
    else:
        deposit.status = "stk_failed"

    db.commit()

    return data
