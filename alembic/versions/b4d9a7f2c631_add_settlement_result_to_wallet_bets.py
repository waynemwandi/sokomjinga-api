"""add settlement result to wallet bets

Revision ID: b4d9a7f2c631
Revises: 75356dd704c8
Create Date: 2026-05-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4d9a7f2c631"
down_revision: Union[str, Sequence[str], None] = "75356dd704c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "wallet_bets",
        sa.Column("settled_payout_cents", sa.Integer(), nullable=True),
    )
    op.add_column(
        "wallet_bets",
        sa.Column("settled_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_wallet_bets_settled_at"),
        "wallet_bets",
        ["settled_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_wallet_bets_settled_at"), table_name="wallet_bets")
    op.drop_column("wallet_bets", "settled_at")
    op.drop_column("wallet_bets", "settled_payout_cents")
