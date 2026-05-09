"""add bio to user_profiles

Revision ID: a7c9d2e4f6b8
Revises: f1b2c3d4e5f6
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7c9d2e4f6b8"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("bio", sa.String(length=280), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "bio")
