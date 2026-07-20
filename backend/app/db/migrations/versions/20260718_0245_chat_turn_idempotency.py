"""Persist chat turn idempotency metadata.

Revision ID: 20260718_0245
Revises: 20260715_0240
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0245"
down_revision: str | None = "20260715_0240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("turn_id", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("route", sa.Text(), nullable=True))

    op.create_index(
        "uq_chat_messages_user_turn_id",
        "chat_messages",
        ["turn_id"],
        unique=True,
        sqlite_where=sa.text("turn_id IS NOT NULL AND role = 'user'"),
    )
    op.create_index(
        "uq_chat_messages_assistant_turn_id",
        "chat_messages",
        ["turn_id"],
        unique=True,
        sqlite_where=sa.text("turn_id IS NOT NULL AND role = 'assistant'"),
    )


def downgrade() -> None:
    op.drop_index("uq_chat_messages_assistant_turn_id", table_name="chat_messages")
    op.drop_index("uq_chat_messages_user_turn_id", table_name="chat_messages")
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("route")
        batch_op.drop_column("turn_id")
