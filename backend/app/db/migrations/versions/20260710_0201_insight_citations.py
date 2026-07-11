"""Add persisted evidence citations to cached insights.

Revision ID: 20260710_0201
Revises: 20260709_0159
Create Date: 2026-07-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0201"
down_revision: str | None = "20260709_0159"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "insights",
        sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("insights", "citations_json")
