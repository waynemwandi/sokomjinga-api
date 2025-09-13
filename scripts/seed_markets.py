# scripts/seed_markets.py
from sqlalchemy import select

from app.db.models import Market
from app.db.session import SessionLocal

SEEDS = [
    "Will Ruto serve WANTAM?",
    "Will Kenya qualify for AFCON 2025?",
    "Will Manchester City win the Premier League this season?",
    "Will Bitcoin close above $100,000 by year-end?",
    "Will crude oil trade above $100 per barrel this quarter?",
    "Will the NSE 20 index finish the year higher than it started?",
    "Will Nairobi record a daily high above 35°C this month?",
    "Will a nationwide internet outage last more than 1 hour this quarter?",
    "Will a new international airline launch direct flights to Nairobi this year?",
    "Will the Safari Rally remain on the WRC calendar next season?",
]


def main():
    db = SessionLocal()
    try:
        # existing titles as a set of strings
        existing = set(db.execute(select(Market.title)).scalars())
        to_add = [Market(title=t, description=None) for t in SEEDS if t not in existing]
        if to_add:
            db.add_all(to_add)
            db.commit()
            print(f"Seeded {len(to_add)} markets.")
        else:
            print("Markets already present; skipping.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
