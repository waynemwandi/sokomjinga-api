"""add username to user_profiles

Revision ID: f1b2c3d4e5f6
Revises: d8e9f1a2b3c4
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d8e9f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("username", sa.String(length=24), nullable=True))
    op.create_index(op.f("ix_user_profiles_username"), "user_profiles", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_profiles_username"), table_name="user_profiles")
    op.drop_column("user_profiles", "username")
