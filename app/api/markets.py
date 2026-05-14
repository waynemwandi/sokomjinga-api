# app/api/markets.py
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.services.notifications import send_bet_confirmation, send_market_created
from app.services.settlement import settle_market

router = APIRouter()
questions_router = APIRouter(prefix="/market-questions", tags=["market-questions"])


# ----------- Helpers -----------
DEFAULT_STARTER_POOL_CENTS = 100  # KES 1 on each Yes/No side


def get_market_starter_pool_cents(market: Market) -> int:
    return max(0, int(getattr(market, "starter_pool_cents", 100) or 0))


def market_to_dict(m: Market, db: Session) -> dict:
    volume_cents = compute_market_volume_cents(db, m.id)
    starter_pool_cents = get_market_starter_pool_cents(m)

    settlement = (
        db.query(models.MarketSettlement)
        .filter(models.MarketSettlement.market_id == m.id)
        .first()
    )
    settlement_outcome = None
    if settlement:
        settlement_outcome = next(
            (o for o in (m.outcomes or []) if o.id == settlement.outcome_id),
            None,
        )

    # compute stake per outcome
    stakes = (
        db.query(
            models.WalletBet.outcome_id,
            func.coalesce(func.sum(models.WalletBet.amount_cents), 0),
        )
        .filter(
            models.WalletBet.market_id == m.id,
            models.WalletBet.status == "open",
        )
        .group_by(models.WalletBet.outcome_id)
        .all()
    )

    stake_map = {outcome_id: total for outcome_id, total in stakes}

    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "status": m.status,
        "is_archived": m.is_archived,
        "image_url": m.image_url,
        "category": m.category,
        "close_at": m.close_at,
        "projected_end_date": m.projected_end_date,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "volume_cents": volume_cents,
        "starter_pool_cents": starter_pool_cents,
        "winning_outcome_id": settlement.outcome_id if settlement else None,
        "winning_outcome_label": settlement_outcome.label if settlement_outcome else None,
        "settled_at": settlement.created_at if settlement else None,
        "settlement": {
            "id": settlement.id,
            "outcome_id": settlement.outcome_id,
            "outcome_label": settlement_outcome.label if settlement_outcome else None,
            "total_pool_cents": settlement.total_pool_cents,
            "fee_cents": settlement.fee_cents,
            "created_at": settlement.created_at,
        }
        if settlement
        else None,
        "outcomes": [
            {
                "id": o.id,
                "label": o.label,
                "price_cents": o.price_cents,
                "real_stake_cents": stake_map.get(o.id, 0),
                "starter_pool_cents": starter_pool_cents,
                "display_pool_cents": stake_map.get(o.id, 0) + starter_pool_cents,
                "total_stake_cents": stake_map.get(o.id, 0),
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


def coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def parse_optional_datetime(value, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field_name} must be ISO8601")


def question_market_title(question_title: str, option_label: str) -> str:
    return f"{question_title} - {option_label}"


def add_yes_no_outcomes(db: Session, market: Market) -> None:
    db.add_all(
        [
            Outcome(
                market_id=market.id,
                label="Yes",
                price_cents=50,
                status="open",
            ),
            Outcome(
                market_id=market.id,
                label="No",
                price_cents=50,
                status="open",
            ),
        ]
    )
    db.flush()
    recompute_market_prices(db, market)


def get_binary_outcome(market: Market, label: str) -> Outcome | None:
    lower = label.lower()
    return next(
        (o for o in (market.outcomes or []) if (o.label or "").strip().lower() == lower),
        None,
    )


def settle_empty_market(db: Session, market: Market, outcome: Outcome) -> dict:
    """Settle a market with no real bets without moving wallet money."""
    existing = (
        db.query(models.MarketSettlement)
        .filter(models.MarketSettlement.market_id == market.id)
        .first()
    )
    if existing:
        raise RuntimeError("Market already settled")

    settlement = models.MarketSettlement(
        market_id=market.id,
        outcome_id=outcome.id,
        total_pool_cents=0,
        fee_cents=0,
    )
    market.status = "settled"
    db.add(settlement)
    db.commit()
    db.refresh(settlement)

    return {
        "status": "settled",
        "market_id": market.id,
        "outcome_id": outcome.id,
        "total_pool_cents": 0,
        "fee_cents": 0,
        "payouts": [],
    }


def count_open_bets(db: Session, market_id: str) -> int:
    return (
        db.query(func.count(models.WalletBet.id))
        .filter(
            models.WalletBet.market_id == market_id,
            models.WalletBet.status == "open",
        )
        .scalar()
        or 0
    )


def question_to_dict(q: models.MarketQuestion, db: Session) -> dict:
    child_markets = sorted(q.markets or [], key=lambda m: m.option_order)
    options = []
    total_volume_cents = 0
    for child in child_markets:
        child_dict = market_to_dict(child, db)
        total_volume_cents += child_dict.get("volume_cents", 0) or 0
        yes = next(
            (
                o
                for o in child_dict.get("outcomes", [])
                if (o.get("label") or "").lower() == "yes"
            ),
            None,
        )
        no = next(
            (
                o
                for o in child_dict.get("outcomes", [])
                if (o.get("label") or "").lower() == "no"
            ),
            None,
        )
        options.append(
            {
                "id": child.id,
                "market_id": child.id,
                "label": child.option_label or child.title,
                "order": child.option_order,
                "status": child.status,
                "yes_price_cents": yes.get("price_cents") if yes else None,
                "no_price_cents": no.get("price_cents") if no else None,
                "yes_outcome_id": yes.get("id") if yes else None,
                "no_outcome_id": no.get("id") if no else None,
                "volume_cents": child_dict.get("volume_cents", 0),
                "market": child_dict,
            }
        )

    return {
        "id": q.id,
        "title": q.title,
        "description": q.description,
        "status": q.status,
        "is_archived": q.is_archived,
        "image_url": q.image_url,
        "category": q.category,
        "close_at": q.close_at,
        "projected_end_date": q.projected_end_date,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
        "volume_cents": total_volume_cents,
        "options": options,
    }


def recompute_market_prices(db: Session, market: Market) -> None:
    """
    Recompute YES/NO prices from real open stake plus a tiny starter pool.

    price_cents ~ probability * 100, where:
      prob_yes = (stake_yes + starter) / (stake_yes + stake_no + 2 * starter)
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

    K = get_market_starter_pool_cents(market)

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
            total_stake_cents=stake_yes + K,
        )
    )
    snapshots.append(
        MarketPriceHistory(
            market_id=market.id,
            outcome_id=no.id,
            price_cents=no.price_cents or 0,
            total_stake_cents=stake_no + K,
        )
    )

    db.add_all(snapshots)


def compute_market_volume_cents(db: Session, market_id: str) -> int:
    return (
        db.query(func.coalesce(func.sum(models.WalletBet.amount_cents), 0))
        .filter(
            models.WalletBet.market_id == market_id,
        )
        .scalar()
        or 0
    )


# ---------- Markets ----------
@router.get("")  # List markets - PUBLIC by default; admins can include archived
def list_markets(
    request: Request,
    include_archived: bool = False,
    include_group_children: bool = False,
    db: Session = Depends(get_db),
):
    if include_archived:
        user = deps.get_current_user(request, db)
        if not getattr(user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )

    query = db.query(Market)
    if not include_archived:
        query = query.filter(Market.is_archived.is_(False))
    if not include_group_children:
        query = query.filter(Market.question_id.is_(None))

    rows = query.order_by(Market.created_at.desc()).all()
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
    try:
        m.starter_pool_cents = int(
            payload.get("starter_pool_cents") or DEFAULT_STARTER_POOL_CENTS
        )
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="starter_pool_cents must be an integer",
        )
    if m.starter_pool_cents < 0:
        raise HTTPException(
            status_code=400,
            detail="starter_pool_cents must be zero or greater",
        )

    m.close_at = parse_optional_datetime(payload.get("close_at"), "close_at")
    m.projected_end_date = parse_optional_datetime(
        payload.get("projected_end_date"),
        "projected_end_date",
    )

    m.status = (payload.get("status") or "open").strip()
    m.is_archived = coerce_bool(payload.get("is_archived", False))

    db.add(m)
    db.commit()
    db.refresh(m)
    add_yes_no_outcomes(db, m)
    db.commit()
    try:
        send_market_created(db, m)
    except Exception:
        pass

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
    if "projected_end_date" in payload:
        ped = payload.get("projected_end_date")
        if ped:
            try:
                m.projected_end_date = datetime.fromisoformat(ped)
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="projected_end_date must be ISO8601",
                )
        else:
            m.projected_end_date = None

    if "status" in payload:
        m.status = (payload.get("status") or "").strip() or m.status

    if "is_archived" in payload:
        m.is_archived = coerce_bool(payload.get("is_archived"))

    if "starter_pool_cents" in payload:
        try:
            starter_pool_cents = int(payload.get("starter_pool_cents"))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="starter_pool_cents must be an integer",
            )
        if starter_pool_cents < 0:
            raise HTTPException(
                status_code=400,
                detail="starter_pool_cents must be zero or greater",
            )
        m.starter_pool_cents = starter_pool_cents
        recompute_market_prices(db, m)

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


@router.post(
    "/{market_id}/settle",
    dependencies=[Depends(deps.require_admin)],
)
def settle_market_endpoint(
    market_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    outcome_id = payload.get("outcome_id")
    if not outcome_id:
        raise HTTPException(status_code=400, detail="outcome_id is required")

    try:
        return settle_market(db, market_id, outcome_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ---------- Market questions (one question, many Yes/No child markets) ----------
@questions_router.get("")
def list_market_questions(
    request: Request,
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    if include_archived:
        user = deps.get_current_user(request, db)
        if not getattr(user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )

    query = db.query(models.MarketQuestion)
    if not include_archived:
        query = query.filter(models.MarketQuestion.is_archived.is_(False))

    rows = query.order_by(models.MarketQuestion.created_at.desc()).all()
    return [question_to_dict(q, db) for q in rows]


@questions_router.get("/{question_id}")
def get_market_question(question_id: str, db: Session = Depends(get_db)):
    q = db.query(models.MarketQuestion).filter(models.MarketQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Market question not found")
    return question_to_dict(q, db)


@questions_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(deps.require_admin)],
)
def create_market_question(payload: dict, db: Session = Depends(get_db)):
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    raw_options = payload.get("options") or []
    if not isinstance(raw_options, list) or len(raw_options) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least two options are required",
        )

    labels: list[str] = []
    for item in raw_options:
        label = (item.get("label") if isinstance(item, dict) else str(item)).strip()
        if not label:
            raise HTTPException(status_code=400, detail="Every option needs a label")
        labels.append(label)

    if len({label.lower() for label in labels}) != len(labels):
        raise HTTPException(status_code=400, detail="Option labels must be unique")

    q = models.MarketQuestion(
        title=title,
        description=payload.get("description"),
        image_url=payload.get("image_url"),
        category=payload.get("category"),
        close_at=parse_optional_datetime(payload.get("close_at"), "close_at"),
        projected_end_date=parse_optional_datetime(
            payload.get("projected_end_date"),
            "projected_end_date",
        ),
        status=(payload.get("status") or "open").strip(),
        is_archived=coerce_bool(payload.get("is_archived", False)),
    )
    db.add(q)
    db.flush()

    for index, item in enumerate(raw_options):
        label = (item.get("label") if isinstance(item, dict) else str(item)).strip()
        option_order = (
            int(item.get("order"))
            if isinstance(item, dict) and item.get("order") is not None
            else index
        )
        child = Market(
            question_id=q.id,
            option_label=label,
            option_order=option_order,
            title=question_market_title(q.title, label),
            description=q.description,
            image_url=q.image_url,
            category=q.category,
            close_at=q.close_at,
            projected_end_date=q.projected_end_date,
            status=q.status,
            is_archived=q.is_archived,
            starter_pool_cents=DEFAULT_STARTER_POOL_CENTS,
        )
        db.add(child)
        db.flush()
        add_yes_no_outcomes(db, child)

    db.commit()
    db.refresh(q)
    return question_to_dict(q, db)


@questions_router.put(
    "/{question_id}",
    dependencies=[Depends(deps.require_admin)],
)
def update_market_question(
    question_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    q = db.query(models.MarketQuestion).filter(models.MarketQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Market question not found")

    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        q.title = title
    if "description" in payload:
        q.description = payload.get("description")
    if "image_url" in payload:
        q.image_url = payload.get("image_url")
    if "category" in payload:
        q.category = payload.get("category")
    if "close_at" in payload:
        q.close_at = parse_optional_datetime(payload.get("close_at"), "close_at")
    if "projected_end_date" in payload:
        q.projected_end_date = parse_optional_datetime(
            payload.get("projected_end_date"),
            "projected_end_date",
        )
    if "status" in payload:
        q.status = (payload.get("status") or "").strip() or q.status
    if "is_archived" in payload:
        q.is_archived = coerce_bool(payload.get("is_archived"))

    for child in q.markets or []:
        child.description = q.description
        child.image_url = q.image_url
        child.category = q.category
        child.close_at = q.close_at
        child.projected_end_date = q.projected_end_date
        child.status = q.status
        child.is_archived = q.is_archived
        child.title = question_market_title(q.title, child.option_label or child.title)

    db.commit()
    db.refresh(q)
    return question_to_dict(q, db)


@questions_router.post(
    "/{question_id}/settle",
    dependencies=[Depends(deps.require_admin)],
)
def settle_market_question(
    question_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    winning_market_id = payload.get("winning_market_id") or payload.get("market_id")
    if not winning_market_id:
        raise HTTPException(status_code=400, detail="winning_market_id is required")

    q = db.query(models.MarketQuestion).filter(models.MarketQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Market question not found")
    if q.status != "closed":
        raise HTTPException(
            status_code=400,
            detail="Question must be closed before settlement",
        )

    children = list(q.markets or [])
    winning_child = next((m for m in children if m.id == winning_market_id), None)
    if not winning_child:
        raise HTTPException(status_code=400, detail="Winning option is not in this question")

    results = []
    for child in children:
        outcome_label = "Yes" if child.id == winning_market_id else "No"
        outcome = get_binary_outcome(child, outcome_label)
        if not outcome:
            raise HTTPException(
                status_code=400,
                detail=f"{child.option_label or child.title} has no {outcome_label} outcome",
            )
        child.status = "closed"
        try:
            if count_open_bets(db, child.id) == 0:
                results.append(settle_empty_market(db, child, outcome))
            else:
                results.append(settle_market(db, child.id, outcome.id))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    q.status = "settled"
    db.commit()
    return {"status": "settled", "question_id": q.id, "results": results}


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
        # 1. Create bet (ledger_entry_id will be filled after creating ledger row)
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

        # 2. Create ledger entry: user_wallet -> market_escrow
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

        # 3. Update bet with ledger_entry_id
        bet.ledger_entry_id = ledger.id

        # 4. Update balances
        user_balance.available_cents -= amount_cents
        escrow_balance.available_cents += amount_cents

        # 5. Recompute market prices and record history
        recompute_market_prices(db, market)

        db.commit()
        db.refresh(bet)

        # 6. Send email AFTER successful commit
        try:
            send_bet_confirmation(
                user=user,
                market=market,
                outcome=outcome,
                amount_cents=amount_cents,
            )
        except Exception:
            # Never break core flow because of email
            pass

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
    # 1. Ensure market exists and load outcomes for labels
    market = db.query(Market).filter(Market.id == market_id).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    outcomes_by_id = {o.id: o for o in (market.outcomes or [])}

    # 2. Fetch all history rows for this market (oldest first)
    rows = (
        db.query(models.MarketPriceHistory)
        .filter(models.MarketPriceHistory.market_id == market_id)
        .order_by(models.MarketPriceHistory.created_at.asc())
        .all()
    )

    # 3. Group by outcome_id in Python
    grouped: dict[str, list[models.MarketPriceHistory]] = defaultdict(list)
    for r in rows:
        grouped[r.outcome_id].append(r)

    # 4. Build response: apply `limit` per outcome and serialize
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

