"""Create chat history table.

Revision ID: 20260705_0006
Revises: 20260705_0005
Create Date: 2026-07-05 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0006"
down_revision: str | None = "20260705_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHAT_MESSAGE_ROLES = ("user", "assistant", "tool", "system")


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("tool_outputs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("role", CHAT_MESSAGE_ROLES),
            name="ck_chat_messages_role",
        ),
        sa.CheckConstraint(
            "json_valid(citations_json) AND json_type(citations_json) = 'array'",
            name="ck_chat_messages_citations_json_array",
        ),
        sa.CheckConstraint(
            "json_valid(tool_outputs_json) AND json_type(tool_outputs_json) = 'array'",
            name="ck_chat_messages_tool_outputs_json_array",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_conversation_created_at",
        "chat_messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_created_at", table_name="chat_messages")
    op.drop_table("chat_messages")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"
