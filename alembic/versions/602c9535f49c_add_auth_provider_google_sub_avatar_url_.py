"""add auth_provider/google_sub/avatar_url to user_profiles

Revision ID: 602c9535f49c
Revises: 3aed363c0b56
Create Date: 2025-11-12 13:13:10.934216

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "602c9535f49c"
down_revision: Union[str, Sequence[str], None] = "3aed363c0b56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
