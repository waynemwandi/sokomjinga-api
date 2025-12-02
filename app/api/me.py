# app/api/me.py
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/me", tags=["me"])


# -----------------------------
# Helpers / types
# -----------------------------


class MeStatsOut(BaseModel):
    total_predictions: int
    correct: int
    incorrect: int
    accuracy: float | None  # 0–1, None if no bets

    new_predictions_this_month: int
    correct_this_week: int
    incorrect_this_week: int


class BetHistoryItem(BaseModel):
    id: str
    market_id: str
    outcome_id: str

    title: str
    category: str | None

    prediction: Literal["yes", "no", "other"]
    result: Literal["pending", "correct", "incorrect", "cancelled"]

    created_at: datetime

    stake_cents: int

    yes_percentage: int | None = None
    no_percentage: int | None = None


class PositionsTotals(BaseModel):
    stake_cents: int
    current_value_cents: int
    unrealized_pnl_cents: int


class PositionItem(BaseModel):
    bet_id: str
    market_id: str
    outcome_id: str

    title: str
    category: str | None
    side: Literal["yes", "no", "other"]

    stake_cents: int
    shares: int

    entry_price_cents: int | None = None
    current_price_cents: int | None = None

    current_value_cents: int
    unrealized_pnl_cents: int

    created_at: datetime


class PositionsOut(BaseModel):
    positions: list[PositionItem]
    totals: PositionsTotals


def _normalize_side(label: str | None) -> Literal["yes", "no", "other"]:
    if not label:
        return "other"
    lower = label.strip().lower()
    if lower in {"yes", "y", "true"}:
        return "yes"
    if lower in {"no", "n", "false"}:
        return "no"
    return "other"


def _map_bet_result(
    status: str,
) -> Literal["pending", "correct", "incorrect", "cancelled"]:
    s = (status or "").lower()
    if s == "settled_won":
        return "correct"
    if s == "settled_lost":
        return "incorrect"
    if s == "cancelled":
        return "cancelled"
    # fallback: market not resolved yet
    return "pending"


# -----------------------------
# /me/stats
# -----------------------------


@router.get("/stats", response_model=MeStatsOut)
def get_my_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> MeStatsOut:
    """Aggregate performance stats for the logged-in user."""

    base_q = db.query(models.WalletBet).filter(
        models.WalletBet.user_id == current_user.id
    )

    total = base_q.count()

    correct = base_q.filter(models.WalletBet.status == "settled_won").count()
    incorrect = base_q.filter(models.WalletBet.status == "settled_lost").count()

    # accuracy as 0–1 ratio
    accuracy: float | None
    if total > 0:
        accuracy = correct / total
    else:
        accuracy = None

    now = datetime.utcnow()

    # Start of current month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_predictions_this_month = base_q.filter(
        models.WalletBet.created_at >= month_start
    ).count()

    # Last 7 days
    week_ago = now - timedelta(days=7)
    correct_this_week = base_q.filter(
        models.WalletBet.status == "settled_won",
        models.WalletBet.created_at >= week_ago,
    ).count()
    incorrect_this_week = base_q.filter(
        models.WalletBet.status == "settled_lost",
        models.WalletBet.created_at >= week_ago,
    ).count()

    return MeStatsOut(
        total_predictions=total,
        correct=correct,
        incorrect=incorrect,
        accuracy=accuracy,
        new_predictions_this_month=new_predictions_this_month,
        correct_this_week=correct_this_week,
        incorrect_this_week=incorrect_this_week,
    )


# -----------------------------
# /me/bets  (prediction history)
# -----------------------------


@router.get("/bets", response_model=list[BetHistoryItem])
def get_my_bets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[BetHistoryItem]:
    """
    Return the user's bets joined with market + outcome metadata,
    ready to render in the 'Prediction History' section.
    """

    bets = (
        db.query(models.WalletBet)
        .options(
            joinedload(models.WalletBet.market).joinedload(models.Market.outcomes),
            joinedload(models.WalletBet.outcome),
        )
        .filter(models.WalletBet.user_id == current_user.id)
        .order_by(models.WalletBet.created_at.desc())
        .all()
    )

    items: list[BetHistoryItem] = []

    for b in bets:
        market = b.market
        outcome = b.outcome

        side = _normalize_side(getattr(outcome, "label", None))
        result = _map_bet_result(b.status)

        # Derive yes/no percentages from market outcomes if available
        yes_out = None
        no_out = None
        if market and market.outcomes:
            for o in market.outcomes:
                s = _normalize_side(getattr(o, "label", None))
                if s == "yes" and yes_out is None:
                    yes_out = o
                elif s == "no" and no_out is None:
                    no_out = o

        yes_pct = (
            yes_out.price_cents if yes_out and yes_out.price_cents is not None else None
        )
        no_pct = (
            no_out.price_cents if no_out and no_out.price_cents is not None else None
        )

        items.append(
            BetHistoryItem(
                id=b.id,
                market_id=b.market_id,
                outcome_id=b.outcome_id,
                title=market.title if market else "",
                category=market.category if market else None,
                prediction=side,
                result=result,
                created_at=b.created_at,
                stake_cents=b.amount_cents,
                yes_percentage=yes_pct,
                no_percentage=no_pct,
            )
        )

    return items


# -----------------------------
# /me/positions  (open positions / portfolio)
# -----------------------------


@router.get("/positions", response_model=PositionsOut)
def get_my_positions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> PositionsOut:
    """
    Return open positions for the user.

    NOTE: For now we keep current_value_cents == stake_cents and PnL == 0,
    until you introduce dynamic pricing. The schema is already ready for
    richer logic later.
    """

    bets = (
        db.query(models.WalletBet)
        .options(
            joinedload(models.WalletBet.market),
            joinedload(models.WalletBet.outcome),
        )
        .filter(
            models.WalletBet.user_id == current_user.id,
            models.WalletBet.status == "open",
        )
        .order_by(models.WalletBet.created_at.desc())
        .all()
    )

    positions: list[PositionItem] = []

    total_stake = 0
    total_current = 0

    for b in bets:
        market = b.market
        outcome = b.outcome

        side = _normalize_side(getattr(outcome, "label", None))

        # For now: keep value = stake, pnl = 0.
        stake = b.amount_cents
        current_value = stake
        pnl = 0

        total_stake += stake
        total_current += current_value

        positions.append(
            PositionItem(
                bet_id=b.id,
                market_id=b.market_id,
                outcome_id=b.outcome_id,
                title=market.title if market else "",
                category=market.category if market else None,
                side=side,
                stake_cents=stake,
                shares=b.shares,
                entry_price_cents=b.price_cents_at_bet,
                current_price_cents=outcome.price_cents if outcome else None,
                current_value_cents=current_value,
                unrealized_pnl_cents=pnl,
                created_at=b.created_at,
            )
        )

    totals = PositionsTotals(
        stake_cents=total_stake,
        current_value_cents=total_current,
        unrealized_pnl_cents=total_current - total_stake,
    )

    return PositionsOut(positions=positions, totals=totals)
