# scripts/seed_outcomes.py
from app.db.models import Market, Outcome
from app.db.session import SessionLocal

db = SessionLocal()
try:
    markets = db.query(Market).all()
    added = 0
    for m in markets:
        if not m.outcomes:
            db.add_all(
                [
                    Outcome(market_id=m.id, label="Yes", price_cents=6),
                    Outcome(market_id=m.id, label="No", price_cents=94),
                ]
            )
            added += 2
    if added:
        db.commit()
        print(f"Seeded {added} outcomes.")
    else:
        print("Outcomes already present; skipping.")
finally:
    db.close()
