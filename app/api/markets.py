# app/api/markets.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Market, Outcome
from app.db.session import get_db

router = APIRouter()


def market_to_dict(m: Market) -> dict:
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


@router.get("")
def list_markets(db: Session = Depends(get_db)):
    rows = db.query(Market).order_by(Market.created_at.desc()).all()
    return [market_to_dict(m) for m in rows]


@router.get("/{market_id}")
def get_market(market_id: str, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")
    return market_to_dict(m)


@router.post("", status_code=status.HTTP_201_CREATED)
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
    return market_to_dict(m)


@router.put("/{market_id}")
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
    return market_to_dict(m)


@router.delete("/{market_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_market(market_id: str, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")
    db.delete(m)
    db.commit()
    return None


# ---------- Outcomes (under a market) ----------


@router.post("/{market_id}/outcomes", status_code=status.HTTP_201_CREATED)
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


@router.put("/{market_id}/outcomes/{outcome_id}")
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
    "/{market_id}/outcomes/{outcome_id}", status_code=status.HTTP_204_NO_CONTENT
)
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
    return None
