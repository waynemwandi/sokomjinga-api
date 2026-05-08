# app/services/notifications.py
from app.db import models
from app.services.email import send_email
from app.services.email_templates.bet_confirmation import render_bet_confirmation_email
from app.services.email_templates.deposit_success import render_deposit_success_email
from app.services.email_templates.market_created import render_market_created_email
from app.services.email_templates.settlement_loss import render_settlement_loss_email
from app.services.email_templates.settlement_win import render_settlement_win_email
from app.services.email_templates.withdrawal_completed import (
    render_withdrawal_completed_email,
)
from app.services.email_templates.withdrawal_rejected import (
    render_withdrawal_rejected_email,
)
from app.services.email_templates.withdrawal_requested import (
    render_withdrawal_requested_email,
)


def send_bet_confirmation(user, market, outcome, amount_cents: int):
    """
    Send bet confirmation email
    """

    subject = f"Bet Confirmed — {market.title}"

    body = render_bet_confirmation_email(
        user=user,
        market=market,
        outcome=outcome,
        amount_cents=amount_cents,
    )

    send_email(
        to_email=user.email,
        subject=subject,
        body=body,
    )
    
def send_settlement_win(user, market, payout_cents: int):

    subject = f"You Won — {market.title}"

    body = render_settlement_win_email(
        user=user,
        market=market,
        payout_cents=payout_cents,
    )

    send_email(to_email=user.email, subject=subject, body=body)


def send_settlement_loss(user, market):
    subject = f"Market Settled — {market.title}"

    body = render_settlement_loss_email(
        user=user,
        market=market,
    )

    send_email(to_email=user.email, subject=subject, body=body)
    
def send_market_created(db, market):
    subject = f"New Market — {market.title}"

    body = render_market_created_email(market)

    users = db.query(models.User).all()

    for user in users:
        if not user.email:
            continue

        try:
            send_email(
                to_email=user.email,
                subject=subject,
                body=body,
            )
        except Exception:
            pass


def send_withdrawal_requested(user, withdrawal):
    subject = "Withdrawal Request Received"
    body = render_withdrawal_requested_email(user=user, withdrawal=withdrawal)
    send_email(to_email=user.email, subject=subject, body=body)


def send_withdrawal_completed(user, withdrawal):
    subject = "Withdrawal Sent"
    body = render_withdrawal_completed_email(user=user, withdrawal=withdrawal)
    send_email(to_email=user.email, subject=subject, body=body)


def send_withdrawal_rejected(user, withdrawal):
    subject = "Withdrawal Not Processed"
    body = render_withdrawal_rejected_email(user=user, withdrawal=withdrawal)
    send_email(to_email=user.email, subject=subject, body=body)
