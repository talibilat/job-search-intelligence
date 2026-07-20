"""Persist conversational follow-up prompts.

Revision ID: 20260718_0248
Revises: 20260718_0247
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0248"
down_revision: str | None = "20260718_0247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(
            sa.Column("follow_up_prompts_json", sa.Text(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("follow_up_prompts_json")
