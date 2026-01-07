# app/api/markets.py
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import db
from app.api import deps
from app.api.wallet import (
    get_or_create_market_escrow_account,
    get_or_create_user_wallet,
)
from app.db import models
from app.db.models import Market, Outcome
from app.db.session import get_db

router = APIRouter()


# ----------- Helpers -----------
def market_to_dict(m: Market, db: Session) -> dict:
    volume_cents = compute_market_volume_cents(db, m.id)

    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "status": m.status,
        "image_url": m.image_url,
        "category": m.category,
        "close_at": m.close_at,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "volume_cents": volume_cents,
        "outcomes": [
            {
                "id": o.id,
                "label": o.label,
                "price_cents": o.price_cents,
                "status": o.status,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            }
            for o in (m.outcomes or [])
        ],
    }


def outcome_to_dict(o: Outcome) -> dict:
    return {
        "id": o.id,
        "market_id": o.market_id,
        "label": o.label,
        "price_cents": o.price_cents,
        "status": o.status,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


BASE_LIQUIDITY_CENTS = 100_00  # KES 100.00 as a simple buffer; tweak later if needed


def recompute_market_prices(db: Session, market: Market) -> None:
    """
    Recompute YES/NO prices for a market based on total open stake, with a liquidity buffer.

    price_cents ~ probability * 100, where:
      prob_yes = (stake_yes + K) / (stake_yes + stake_no + 2K)
    """
    outcomes = list(market.outcomes or [])

    # We assume binary YES/NO for now
    yes = next((o for o in outcomes if (o.label or "").lower() == "yes"), None)
    no = next((o for o in outcomes if (o.label or "").lower() == "no"), None)

    if not yes or not no:
        # For now, only handle the standard YES/NO markets
        return

    # Sum all *open* bets per outcome
    stake_yes = (
        db.query(func.coalesce(func.sum(models.WalletBet.amount_cents), 0))
        .filter(
            models.WalletBet.market_id == market.id,
            models.WalletBet.outcome_id == yes.id,
            models.WalletBet.status == "open",
        )
        .scalar()
        or 0
    )

    stake_no = (
        db.query(func.coalesce(func.sum(models.WalletBet.amount_cents), 0))
        .filter(
            models.WalletBet.market_id == market.id,
            models.WalletBet.outcome_id == no.id,
            models.WalletBet.status == "open",
        )
        .scalar()
        or 0
    )

    K = BASE_LIQUIDITY_CENTS

    denom = stake_yes + stake_no + 2 * K
    if denom <= 0:
        # No meaningful volume yet: keep it at 50/50
        yes.price_cents = 50
        no.price_cents = 50
    else:
        prob_yes = (stake_yes + K) / denom
        price_yes = max(1, min(99, int(round(prob_yes * 100))))
        price_no = 100 - price_yes

        yes.price_cents = price_yes
        no.price_cents = price_no

    # Record a history snapshot for both outcomes
    # (only if we have at least some liquidity or stake)
    from app.db.models import MarketPriceHistory  # local import to avoid cycles

    snapshots: list[MarketPriceHistory] = []

    snapshots.append(
        MarketPriceHistory(
            market_id=market.id,
            outcome_id=yes.id,
            price_cents=yes.price_cents or 0,
            total_stake_cents=stake_yes,
        )
    )
    snapshots.append(
        MarketPriceHistory(
            market_id=market.id,
            outcome_id=no.id,
            price_cents=no.price_cents or 0,
            total_stake_cents=stake_no,
        )
    )

    db.add_all(snapshots)


def compute_market_volume_cents(db: Session, market_id: str) -> int:
    return (
        db.query(func.coalesce(func.sum(models.WalletBet.amount_cents), 0))
        .filter(
            models.WalletBet.market_id == market_id,
            models.WalletBet.status == "open",
        )
        .scalar()
        or 0
    )


# ---------- Markets ----------
@router.get("")  # List markets - PUBLIC
def list_markets(db: Session = Depends(get_db)):
    rows = db.query(Market).order_by(Market.created_at.desc()).all()
    return [market_to_dict(m, db) for m in rows]


@router.get("/{market_id}")  # Get market by ID - PUBLIC
def get_market(market_id: str, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")
    return market_to_dict(m, db)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(deps.require_admin)],
)  # Create market - ADMIN ONLY
def create_market(payload: dict, db: Session = Depends(get_db)):
    """
    payload keys accepted:
      title (required), description?, image_url?, category?, close_at? (ISO8601), status? ("open"/"closed")
    """
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    m = Market()
    m.title = title
    m.description = payload.get("description")
    m.image_url = payload.get("image_url")
    m.category = payload.get("category")

    close_at = payload.get("close_at")
    if close_at:
        # accept "YYYY-MM-DDTHH:MM:SS" or "YYYY-MM-DD"
        try:
            m.close_at = datetime.fromisoformat(close_at)
        except Exception:
            raise HTTPException(status_code=400, detail="close_at must be ISO8601")

    m.status = (payload.get("status") or "open").strip()

    db.add(m)
    db.commit()
    db.refresh(m)
    # Auto-create YES/NO outcomes at 50/50
    yes = Outcome(
        market_id=m.id,
        label="Yes",
        price_cents=50,
        status="open",
    )
    no = Outcome(
        market_id=m.id,
        label="No",
        price_cents=50,
        status="open",
    )

    db.add_all([yes, no])
    db.commit()
    return market_to_dict(m, db)


@router.put(
    "/{market_id}",
    dependencies=[Depends(deps.require_admin)],
)  # Update market - ADMIN ONLY
def update_market(market_id: str, payload: dict, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")

    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        m.title = title

    if "description" in payload:
        m.description = payload.get("description")

    if "image_url" in payload:
        m.image_url = payload.get("image_url")

    if "category" in payload:
        m.category = payload.get("category")

    if "close_at" in payload:
        close_at = payload.get("close_at")
        if close_at:
            try:
                m.close_at = datetime.fromisoformat(close_at)
            except Exception:
                raise HTTPException(status_code=400, detail="close_at must be ISO8601")
        else:
            m.close_at = None

    if "status" in payload:
        m.status = (payload.get("status") or "").strip() or m.status

    db.add(m)
    db.commit()
    db.refresh(m)
    return market_to_dict(m, db)


@router.delete(
    "/{market_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(deps.require_admin)],
)  # Delete market - ADMIN ONLY
def delete_market(market_id: str, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")
    db.delete(m)
    db.commit()
    return None


# ---------- Outcomes (under a market) ----------
@router.post(
    "/{market_id}/outcomes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(deps.require_admin)],
)  # Add outcome to market - ADMIN ONLY
def add_outcome(market_id: str, payload: dict, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")

    label = (payload.get("label") or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="label is required")

    o = Outcome()
    o.market_id = m.id
    o.label = label
    o.price_cents = payload.get("price_cents")
    o.status = (payload.get("status") or "open").strip()

    db.add(o)
    db.commit()
    db.refresh(o)
    return outcome_to_dict(o)


@router.put(
    "/{market_id}/outcomes/{outcome_id}",
    dependencies=[
        Depends(deps.require_admin),
    ],
)  # Update outcome - ADMIN ONLY
def update_outcome(
    market_id: str, outcome_id: str, payload: dict, db: Session = Depends(get_db)
):
    o = (
        db.query(Outcome)
        .filter(Outcome.id == outcome_id, Outcome.market_id == market_id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Outcome not found")

    if "label" in payload:
        label = (payload.get("label") or "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="label cannot be empty")
        o.label = label

    if "price_cents" in payload:
        o.price_cents = payload.get("price_cents")

    if "status" in payload:
        o.status = (payload.get("status") or "").strip() or o.status

    db.add(o)
    db.commit()
    db.refresh(o)
    return outcome_to_dict(o)


@router.delete(
    "/{market_id}/outcomes/{outcome_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(deps.require_admin)],
)  # Delete outcome - ADMIN ONLY
def delete_outcome(market_id: str, outcome_id: str, db: Session = Depends(get_db)):
    o = (
        db.query(Outcome)
        .filter(Outcome.id == outcome_id, Outcome.market_id == market_id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Outcome not found")
    db.delete(o)
    db.commit()
    return None


# ---------- Bets (user positions on outcomes) ----------
@router.post("/{market_id}/bets", status_code=status.HTTP_201_CREATED)
def place_bet(
    market_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(deps.get_current_user),
):
    """
    Place a bet on a given outcome in this market.

    Body:
    {
        "outcome_id": "<uuid>",
        "amount_cents": 5000   # e.g. 50 KES if your wallet uses "cents" = 1/100 KES
    }
    """
    outcome_id = (payload.get("outcome_id") or "").strip()
    amount_cents = payload.get("amount_cents")

    # Basic validation
    if not outcome_id:
        raise HTTPException(status_code=400, detail="outcome_id is required")

    try:
        amount_cents = int(amount_cents)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount_cents must be an integer")

    if amount_cents <= 0:
        raise HTTPException(
            status_code=400, detail="amount_cents must be greater than zero"
        )

    # Load market and outcome
    market = db.query(Market).filter(Market.id == market_id).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    if market.status != "open":
        raise HTTPException(status_code=400, detail="Market is not open")

    # Optional: check close_at
    if market.close_at and market.close_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Market is closed")

    outcome = (
        db.query(Outcome)
        .filter(Outcome.id == outcome_id, Outcome.market_id == market_id)
        .first()
    )
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found")

    if outcome.status != "open":
        raise HTTPException(status_code=400, detail="Outcome is not open")

    # Fetch user wallet + market escrow system account
    user_wallet = get_or_create_user_wallet(db, user)
    escrow_account = get_or_create_market_escrow_account(db)

    # Fetch balances (assumes a WalletBalance row exists for each)
    user_balance = (
        db.query(models.WalletBalance)
        .filter(models.WalletBalance.account_id == user_wallet.id)
        .with_for_update()
        .first()
    )
    escrow_balance = (
        db.query(models.WalletBalance)
        .filter(models.WalletBalance.account_id == escrow_account.id)
        .with_for_update()
        .first()
    )

    if not user_balance:
        raise HTTPException(status_code=500, detail="User wallet balance not found")

    if user_balance.available_cents < amount_cents:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    # For now: 1 share, price = amount_cents / 100 (approx KES value)
    shares = 1
    price_cents_at_bet = amount_cents  # simple placeholder

    # Create a bet -> ledger entry -> link them in one transaction
    try:
        # 1) Create bet (ledger_entry_id will be filled after creating ledger row)
        bet = models.WalletBet(
            user_id=user.id,
            market_id=market.id,
            outcome_id=outcome.id,
            amount_cents=amount_cents,
            shares=shares,
            price_cents_at_bet=price_cents_at_bet,
            status="open",
        )
        db.add(bet)
        db.flush()  # bet.id available

        # 2) Create ledger entry: user_wallet -> market_escrow
        ledger = models.WalletLedgerEntry(
            debit_account_id=user_wallet.id,
            credit_account_id=escrow_account.id,
            amount_cents=amount_cents,
            currency=user_wallet.currency,
            kind="bet_lock",
            reference_type="wallet_bet",
            reference_id=bet.id,
            description=f"Bet on outcome {outcome.label} in market {market.title}",
        )
        db.add(ledger)
        db.flush()  # ledger.id available

        # 3) Update bet with ledger_entry_id
        bet.ledger_entry_id = ledger.id

        # 4) Update balances
        user_balance.available_cents -= amount_cents
        escrow_balance.available_cents += amount_cents

        # 5) Recompute market prices and record history
        recompute_market_prices(db, market)

        db.commit()
        db.refresh(bet)

    except Exception:
        db.rollback()
        raise

    return {
        "id": bet.id,
        "user_id": bet.user_id,
        "market_id": bet.market_id,
        "outcome_id": bet.outcome_id,
        "amount_cents": bet.amount_cents,
        "shares": bet.shares,
        "price_cents_at_bet": bet.price_cents_at_bet,
        "status": bet.status,
        "ledger_entry_id": bet.ledger_entry_id,
        "created_at": bet.created_at,
        "updated_at": bet.updated_at,
    }


# ---------- Public price history ----------


@router.get("/{market_id}/price-history")
def get_market_price_history(
    market_id: str,
    limit: int = 200,  # max points per outcome
    db: Session = Depends(get_db),
):
    """
    Public timeseries of price snapshots for this market.

    Returns the last `limit` points per outcome, ordered by time ascending.
    """
    # 1) Ensure market exists and load outcomes for labels
    market = db.query(Market).filter(Market.id == market_id).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    outcomes_by_id = {o.id: o for o in (market.outcomes or [])}

    # 2) Fetch all history rows for this market (oldest first)
    rows = (
        db.query(models.MarketPriceHistory)
        .filter(models.MarketPriceHistory.market_id == market_id)
        .order_by(models.MarketPriceHistory.created_at.asc())
        .all()
    )

    # 3) Group by outcome_id in Python
    grouped: dict[str, list[models.MarketPriceHistory]] = defaultdict(list)
    for r in rows:
        grouped[r.outcome_id].append(r)

    # 4) Build response: apply `limit` per outcome and serialize
    resp_outcomes: list[dict] = []
    for outcome_id, history_rows in grouped.items():
        # take last `limit` points, but keep time ascending
        sliced = history_rows[-limit:]
        points = [
            {
                "t": h.created_at,
                "price_cents": h.price_cents,
                "total_stake_cents": int(h.total_stake_cents or 0),
            }
            for h in sliced
        ]

        outcome_obj = outcomes_by_id.get(outcome_id)
        resp_outcomes.append(
            {
                "outcome_id": outcome_id,
                "label": outcome_obj.label if outcome_obj else None,
                "points": points,
            }
        )

    return {
        "market_id": market.id,
        "outcomes": resp_outcomes,
    }
