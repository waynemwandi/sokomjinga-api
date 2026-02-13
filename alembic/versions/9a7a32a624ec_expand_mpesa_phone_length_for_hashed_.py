"""expand mpesa_phone length for hashed MSISDN

Revision ID: 9a7a32a624ec
Revises: 165cda07c8bb
Create Date: 2026-02-13 12:36:57.531559

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a7a32a624ec"
down_revision: Union[str, Sequence[str], None] = "165cda07c8bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """Upgrade schema."""
    op.alter_column(
        "wallet_deposits",
        "mpesa_phone",
        existing_type=sa.String(length=20),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade():
    """Downgrade schema."""
    op.alter_column(
        "wallet_deposits",
        "mpesa_phone",
        existing_type=sa.String(length=100),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
