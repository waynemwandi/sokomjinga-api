# app/api/me.py
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
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
    market_status: str | None = None
    close_at: datetime | None = None
    projected_end_date: datetime | None = None

    prediction: Literal["yes", "no", "other"]
    result: Literal["pending", "correct", "incorrect", "cancelled"]

    created_at: datetime
    settled_at: datetime | None = None

    stake_cents: int
    anticipated_payout_cents: int | None = None
    possible_gain_cents: int | None = None
    settled_payout_cents: int | None = None

    yes_percentage: int | None = None
    no_percentage: int | None = None


class PositionsTotals(BaseModel):
    count: int
    stake_cents: int
    possible_payout_cents: int
    possible_gain_cents: int

    # Backward-compatible aliases for older frontend code.
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

    possible_payout_cents: int
    possible_gain_cents: int

    # Backward-compatible aliases for older frontend code.
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


def _estimate_possible_payout_cents(
    *,
    stake_cents: int,
    selected_pool_cents: int,
    other_pool_cents: int,
    fee_rate_bps: int,
) -> int:
    """
    Estimate what this bet would receive if its selected side wins using
    current open market pools. This mirrors settlement pool-share math, but it
    is not guaranteed because market pools can change before settlement.
    """
    total_pool = selected_pool_cents + other_pool_cents
    if stake_cents <= 0 or selected_pool_cents <= 0 or total_pool <= 0:
        return 0

    fee_cents = (total_pool * fee_rate_bps) // 10000
    distributable_cents = max(0, total_pool - fee_cents)

    return (stake_cents * distributable_cents) // selected_pool_cents


def _open_pools_by_market(
    db: Session,
    market_ids: set[str],
) -> dict[str, dict[str, int]]:
    if not market_ids:
        return {}

    rows = (
        db.query(
            models.WalletBet.market_id,
            models.WalletBet.outcome_id,
            func.coalesce(func.sum(models.WalletBet.amount_cents), 0),
        )
        .filter(
            models.WalletBet.market_id.in_(market_ids),
            models.WalletBet.status == "open",
        )
        .group_by(models.WalletBet.market_id, models.WalletBet.outcome_id)
        .all()
    )

    pools: dict[str, dict[str, int]] = {}
    for market_id, outcome_id, total in rows:
        pools.setdefault(market_id, {})[outcome_id] = int(total or 0)

    return pools


def _estimated_payout_for_bet(
    bet: models.WalletBet,
    pools_by_market: dict[str, dict[str, int]],
) -> int:
    market = bet.market
    pool_by_outcome = pools_by_market.get(bet.market_id, {})
    starter_pool_cents = max(
        0,
        int(getattr(market, "starter_pool_cents", 100) or 0),
    )
    selected_pool = pool_by_outcome.get(bet.outcome_id, 0) + starter_pool_cents
    other_pool = sum(
        total
        for outcome_id, total in pool_by_outcome.items()
        if outcome_id != bet.outcome_id
    ) + starter_pool_cents
    fee_rate_bps = market.fee_rate_bps if market else 500

    return _estimate_possible_payout_cents(
        stake_cents=bet.amount_cents,
        selected_pool_cents=selected_pool,
        other_pool_cents=other_pool,
        fee_rate_bps=fee_rate_bps,
    )


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

    pools_by_market = _open_pools_by_market(db, {b.market_id for b in bets})
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

        anticipated_payout: int | None = None
        possible_gain: int | None = None
        if b.status == "open":
            anticipated_payout = _estimated_payout_for_bet(b, pools_by_market)
            possible_gain = anticipated_payout - b.amount_cents

        items.append(
            BetHistoryItem(
                id=b.id,
                market_id=b.market_id,
                outcome_id=b.outcome_id,
                title=market.title if market else "",
                category=market.category if market else None,
                market_status=market.status if market else None,
                close_at=market.close_at if market else None,
                projected_end_date=market.projected_end_date if market else None,
                prediction=side,
                result=result,
                created_at=b.created_at,
                settled_at=b.settled_at,
                stake_cents=b.amount_cents,
                anticipated_payout_cents=anticipated_payout,
                possible_gain_cents=possible_gain,
                settled_payout_cents=b.settled_payout_cents,
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

    possible_payout_cents estimates what the user could receive if the selected
    side wins using current open market pools. It is an estimate, not a
    guarantee, because more bets can arrive before settlement.
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

    pools_by_market = _open_pools_by_market(db, {b.market_id for b in bets})

    positions: list[PositionItem] = []

    total_stake = 0
    total_possible_payout = 0

    for b in bets:
        market = b.market
        outcome = b.outcome

        side = _normalize_side(getattr(outcome, "label", None))
        stake = b.amount_cents

        possible_payout = _estimated_payout_for_bet(b, pools_by_market)
        possible_gain = possible_payout - stake

        total_stake += stake
        total_possible_payout += possible_payout

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
                possible_payout_cents=possible_payout,
                possible_gain_cents=possible_gain,
                current_value_cents=possible_payout,
                unrealized_pnl_cents=possible_gain,
                created_at=b.created_at,
            )
        )

    total_possible_gain = total_possible_payout - total_stake

    totals = PositionsTotals(
        count=len(positions),
        stake_cents=total_stake,
        possible_payout_cents=total_possible_payout,
        possible_gain_cents=total_possible_gain,
        current_value_cents=total_possible_payout,
        unrealized_pnl_cents=total_possible_gain,
    )

    return PositionsOut(positions=positions, totals=totals)
