"""Backfill exact settled payout fields on wallet_bets.

Dry-run by default:
    python scripts/backfill_settled_bet_payouts.py

Write reviewed changes:
    python scripts/backfill_settled_bet_payouts.py --write

Overwrite existing settled_payout_cents / settled_at values:
    python scripts/backfill_settled_bet_payouts.py --write --overwrite
"""

import argparse
import os
import sys
from dataclasses import dataclass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@dataclass
class BackfillSummary:
    markets_seen: int = 0
    markets_updated: int = 0
    bets_seen: int = 0
    bets_to_update: int = 0
    total_payout_cents: int = 0


def compute_payouts(bets: list, settlement) -> dict[str, int]:
    winning_pool = sum(
        b.amount_cents for b in bets if b.outcome_id == settlement.outcome_id
    )
    distributable = settlement.total_pool_cents - settlement.fee_cents

    payouts: dict[str, int] = {}
    if winning_pool <= 0 or distributable <= 0:
        return {b.id: 0 for b in bets}

    for bet in bets:
        if bet.outcome_id == settlement.outcome_id:
            payouts[bet.id] = (bet.amount_cents * distributable) // winning_pool
        else:
            payouts[bet.id] = 0

    remainder = distributable - sum(payouts.values())
    winners = sorted(
        [b for b in bets if payouts.get(b.id, 0) > 0],
        key=lambda b: b.id,
    )

    for i in range(remainder):
        payouts[winners[i].id] += 1

    return payouts


def run(*, write: bool, overwrite: bool) -> BackfillSummary:
    from app.db.models import MarketSettlement, WalletBet
    from app.db.session import SessionLocal

    summary = BackfillSummary()
    db = SessionLocal()

    try:
        settlements = db.query(MarketSettlement).order_by(MarketSettlement.created_at).all()
        summary.markets_seen = len(settlements)

        for settlement in settlements:
            bets = (
                db.query(WalletBet)
                .filter(
                    WalletBet.market_id == settlement.market_id,
                    WalletBet.status.in_(["settled_won", "settled_lost"]),
                )
                .order_by(WalletBet.id)
                .all()
            )
            if not bets:
                continue

            summary.bets_seen += len(bets)
            payouts = compute_payouts(bets, settlement)
            market_changed = False

            for bet in bets:
                if not overwrite and bet.settled_payout_cents is not None:
                    continue

                payout = payouts.get(bet.id, 0)
                summary.bets_to_update += 1
                summary.total_payout_cents += payout
                market_changed = True

                print(
                    "UPDATE"
                    f" market={settlement.market_id}"
                    f" bet={bet.id}"
                    f" status={bet.status}"
                    f" stake_cents={bet.amount_cents}"
                    f" payout_cents={payout}"
                    f" settled_at={settlement.created_at.isoformat()}"
                )

                if write:
                    bet.settled_payout_cents = payout
                    bet.settled_at = settlement.created_at

            if market_changed:
                summary.markets_updated += 1

        if write:
            db.commit()
        else:
            db.rollback()

        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Persist updates.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing settled payout fields.",
    )
    args = parser.parse_args()

    summary = run(write=args.write, overwrite=args.overwrite)
    mode = "WRITE" if args.write else "DRY RUN"
    print(
        f"{mode}: markets_seen={summary.markets_seen} "
        f"markets_updated={summary.markets_updated} "
        f"bets_seen={summary.bets_seen} "
        f"bets_to_update={summary.bets_to_update} "
        f"total_payout_cents={summary.total_payout_cents}"
    )


if __name__ == "__main__":
    main()
