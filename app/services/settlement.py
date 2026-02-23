# app/services/settlement.py
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.wallet import (
    get_or_create_market_escrow_account,
    get_or_create_platform_fee_account,
    get_or_create_user_wallet,
)
from app.db.models import (
    Market,
    MarketSettlement,
    Outcome,
    WalletBalance,
    WalletBet,
    WalletLedgerEntry,
)

logger = logging.getLogger("maoni.settlement")


def settle_market(db: Session, market_id: str, outcome_id: str):
    logger.info("settlement_start market_id=%s outcome_id=%s", market_id, outcome_id)

    # 1. Lock market
    market = db.query(Market).filter(Market.id == market_id).with_for_update().first()

    if not market:
        raise Exception("Market not found")

    if market.status != "closed":
        raise Exception("Market must be closed before settlement")

    # 2. Prevent double settlement
    existing = (
        db.query(MarketSettlement)
        .filter(MarketSettlement.market_id == market.id)
        .first()
    )

    if existing:
        raise Exception("Market already settled")

    # 3. Validate outcome
    outcome = (
        db.query(Outcome)
        .filter(Outcome.id == outcome_id, Outcome.market_id == market.id)
        .first()
    )

    if not outcome:
        raise Exception("Invalid outcome")

    # 4. Load bets
    bets = (
        db.query(WalletBet)
        .filter(
            WalletBet.market_id == market.id,
            WalletBet.status == "open",
        )
        .all()
    )

    if not bets:
        raise Exception("No bets to settle")

    # 5. Aggregate pools using outcome_id only (label-agnostic)
    winning_pool = sum(b.amount_cents for b in bets if b.outcome_id == outcome_id)
    losing_pool = sum(b.amount_cents for b in bets if b.outcome_id != outcome_id)
    P = winning_pool + losing_pool

    if P <= 0:
        raise ValueError("Invalid pool")

    # 6. Load system accounts FIRST
    escrow = get_or_create_market_escrow_account(db)
    platform = get_or_create_platform_fee_account(db)

    # 7. Compute per-market escrow from ledger
    market_escrow_from_ledger = (
        db.query(func.coalesce(func.sum(WalletLedgerEntry.amount_cents), 0))
        .join(WalletBet, WalletBet.id == WalletLedgerEntry.reference_id)
        .filter(
            WalletLedgerEntry.kind == "bet_lock",
            WalletLedgerEntry.credit_account_id == escrow.id,
            WalletBet.market_id == market.id,
        )
        .scalar()
    )

    if market_escrow_from_ledger != P:
        raise RuntimeError(
            f"Per-market escrow mismatch. Ledger={market_escrow_from_ledger}, Bets={P}"
        )

    escrow_bal = (
        db.query(WalletBalance)
        .filter(WalletBalance.account_id == escrow.id)
        .with_for_update()
        .one()
    )

    platform_bal = (
        db.query(WalletBalance)
        .filter(WalletBalance.account_id == platform.id)
        .with_for_update()
        .one()
    )

    # Safety check: escrow should equal total pool for this market
    if escrow_bal.available_cents < P:
        # This is serious: you have less money in escrow than bets claim
        raise RuntimeError("Escrow balance less than total pool. Refusing to settle.")

    # 8. Determine economic branch
    payouts: list[dict] = []
    fee_cents = 0

    # Case: no winners
    if winning_pool == 0:
        fee_cents = P
        payouts = [{"bet": b, "payout": 0} for b in bets]

    else:
        fee_cents = (P * market.fee_rate_bps) // 10000
        distributable = P - fee_cents

        for b in bets:
            if b.outcome_id == outcome_id:
                payout = (b.amount_cents * distributable) // winning_pool
                payouts.append({"bet": b, "payout": payout})
            else:
                payouts.append({"bet": b, "payout": 0})

        remainder = distributable - sum(x["payout"] for x in payouts)

        winners = [x for x in payouts if x["payout"] > 0]
        winners.sort(key=lambda x: x["bet"].id)

        for i in range(remainder):
            winners[i]["payout"] += 1

    # 9. Apply ledger entries
    for x in payouts:
        bet = x["bet"]
        payout = x["payout"]

        if payout > 0:
            user_wallet = get_or_create_user_wallet(db, bet.user)

            user_bal = (
                db.query(WalletBalance)
                .filter(WalletBalance.account_id == user_wallet.id)
                .with_for_update()
                .one()
            )

            entry = WalletLedgerEntry(
                debit_account_id=escrow.id,
                credit_account_id=user_wallet.id,
                amount_cents=payout,
                currency="KES",
                kind="settlement_payout",
                reference_type="market",
                reference_id=market.id,
            )
            db.add(entry)

            escrow_bal.available_cents -= payout
            user_bal.available_cents += payout

            bet.status = "settled_won"
        else:
            bet.status = "settled_lost"

    # Fee transfer
    if fee_cents > 0:
        entry = WalletLedgerEntry(
            debit_account_id=escrow.id,
            credit_account_id=platform.id,
            amount_cents=fee_cents,
            currency="KES",
            kind="settlement_fee",
            reference_type="market",
            reference_id=market.id,
        )
        db.add(entry)

        escrow_bal.available_cents -= fee_cents
        platform_bal.available_cents += fee_cents

    # 10. Insert settlement record
    settlement = MarketSettlement(
        market_id=market.id,
        outcome_id=outcome_id,
        total_pool_cents=P,
        fee_cents=fee_cents,
    )
    db.add(settlement)

    # 11. Mark market settled
    market.status = "settled"

    db.commit()

    return {"status": "settled", "market_id": market.id}
