"""add is_admin to users

Revision ID: 3aed363c0b56
Revises: 2945f1dd2a15
Create Date: 2025-10-30 23:08:46.776507

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3aed363c0b56"
down_revision: Union[str, Sequence[str], None] = "2945f1dd2a15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )
    # optional: remove the default at the schema level after backfilling
    op.alter_column("users", "is_admin", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_admin")
