"""add starter pool to markets

Revision ID: b1c2d3e4f7a9
Revises: a7c9d2e4f6b8
Create Date: 2026-05-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b1c2d3e4f7a9"
down_revision: Union[str, Sequence[str], None] = "a7c9d2e4f6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column(
            "starter_pool_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
    )


def downgrade() -> None:
    op.drop_column("markets", "starter_pool_cents")
