"""Create email backfill state table.

Revision ID: 20260705_0002
Revises: 20260705_0001
Create Date: 2026-07-05 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0002"
down_revision: str | None = "20260705_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_backfill_state",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("next_page_token", sa.Text(), nullable=True),
        sa.Column("processed_page_count", sa.Integer(), nullable=False),
        sa.Column("processed_message_count", sa.Integer(), nullable=False),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("cursor_issued_at", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("provider", "account_id"),
        sa.CheckConstraint("processed_page_count >= 0"),
        sa.CheckConstraint("processed_message_count >= 0"),
    )


def downgrade() -> None:
    op.drop_table("email_backfill_state")
