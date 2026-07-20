"""Persist explicit grounded-answer and refusal state.

Revision ID: 20260718_0246
Revises: 20260718_0245
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0246"
down_revision: str | None = "20260718_0245"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("answer_kind", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("answer_kind")
