"""Create heuristic filter decision audit table.

Revision ID: 20260705_0084
Revises: 20260705_0007
Create Date: 2026-07-05 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0084"
down_revision: str | None = "20260705_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FILTER_DECISION_OUTCOMES = ("candidate", "rejected")


def upgrade() -> None:
    op.create_table(
        "email_filter_decisions",
        sa.Column("email_id", sa.Text(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("outcome", FILTER_DECISION_OUTCOMES),
            name="ck_email_filter_decisions_outcome",
        ),
        sa.ForeignKeyConstraint(["email_id"], ["raw_emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("email_id", "strategy"),
    )
    op.create_index(
        "ix_email_filter_decisions_outcome",
        "email_filter_decisions",
        ["outcome"],
    )
    op.create_index(
        "ix_email_filter_decisions_strategy",
        "email_filter_decisions",
        ["strategy"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_filter_decisions_strategy", table_name="email_filter_decisions")
    op.drop_index("ix_email_filter_decisions_outcome", table_name="email_filter_decisions")
    op.drop_table("email_filter_decisions")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"
