# app/api/health.py
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["system"])
def health():
    return {
        "ok": True,
        "service": "sokomjinga-api",
        "time": datetime.now(timezone.utc).isoformat(),
    }
