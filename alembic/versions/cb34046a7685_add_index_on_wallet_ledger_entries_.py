"""add index on wallet_ledger_entries created_at

Revision ID: cb34046a7685
Revises: 9a7a32a624ec
Create Date: 2026-02-13 13:15:27.243483

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "cb34046a7685"
down_revision: Union[str, Sequence[str], None] = "9a7a32a624ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_wallet_ledger_entries_created_at",
        "wallet_ledger_entries",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wallet_ledger_entries_created_at",
        table_name="wallet_ledger_entries",
    )
