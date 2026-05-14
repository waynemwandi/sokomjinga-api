"""add market questions

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f7a9
Create Date: 2026-05-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f7a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_questions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("close_at", sa.DateTime(), nullable=True),
        sa.Column("projected_end_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("markets", sa.Column("question_id", sa.String(length=36), nullable=True))
    op.add_column("markets", sa.Column("option_label", sa.String(length=128), nullable=True))
    op.add_column(
        "markets",
        sa.Column("option_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index("ix_markets_question_id", "markets", ["question_id"])
    op.create_foreign_key(
        "fk_markets_question_id_market_questions",
        "markets",
        "market_questions",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_markets_question_id_market_questions", "markets", type_="foreignkey")
    op.drop_index("ix_markets_question_id", table_name="markets")
    op.drop_column("markets", "option_order")
    op.drop_column("markets", "option_label")
    op.drop_column("markets", "question_id")
    op.drop_table("market_questions")
