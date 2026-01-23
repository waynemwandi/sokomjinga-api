"""add projected_end_date to markets

Revision ID: dca01aac8b74
Revises: 67597e299baf
Create Date: 2026-01-21 16:24:25.287488

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dca01aac8b74"
down_revision: Union[str, Sequence[str], None] = "67597e299baf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "markets",
        sa.Column("projected_end_date", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("markets", "projected_end_date")
