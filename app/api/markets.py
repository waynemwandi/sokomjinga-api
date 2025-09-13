from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Market
from app.db.session import get_db

router = APIRouter()


@router.get("")
def list_markets(db: Session = Depends(get_db)):
    rows = db.query(Market).order_by(Market.created_at.desc()).all()
    return [
        {
            "id": m.id,
            "title": m.title,
            "description": m.description,
            "status": m.status,
            "image_url": m.image_url,
            "category": m.category,
            "close_at": m.close_at,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }
        for m in rows
    ]


@router.get("/{market_id}")
def get_market(market_id: str, db: Session = Depends(get_db)):
    m = db.query(Market).filter(Market.id == market_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")
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
            }
            for o in m.outcomes
        ],
    }
