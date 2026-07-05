"""Create email sync state table.

Revision ID: 20260705_0001
Revises:
Create Date: 2026-07-05 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_sync_state",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("sync_cursor", sa.Text(), nullable=False),
        sa.Column("cursor_issued_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("provider", "account_id"),
    )


def downgrade() -> None:
    op.drop_table("email_sync_state")
