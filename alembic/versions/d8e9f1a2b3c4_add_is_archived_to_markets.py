"""add is_archived to markets

Revision ID: d8e9f1a2b3c4
Revises: b4d9a7f2c631
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = "d8e9f1a2b3c4"
down_revision = "b4d9a7f2c631"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("markets", "is_archived")
