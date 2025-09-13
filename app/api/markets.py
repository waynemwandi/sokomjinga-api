from fastapi import APIRouter, Depends
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
            "created_at": m.created_at,
        }
        for m in rows
    ]
