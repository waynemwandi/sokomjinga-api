"""add account reference to wallet deposits

Revision ID: e8f9a0b1c2d3
Revises: c2d3e4f5a6b7
Create Date: 2026-05-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wallet_deposits",
        sa.Column("account_reference", sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f("ix_wallet_deposits_account_reference"),
        "wallet_deposits",
        ["account_reference"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_wallet_deposits_account_reference"),
        table_name="wallet_deposits",
    )
    op.drop_column("wallet_deposits", "account_reference")
