"""Create application corrections audit table.

Revision ID: 20260705_0005
Revises: 20260705_0004
Create Date: 2026-07-05 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0005"
down_revision: str | None = "20260705_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORRECTION_TYPES = ("merge", "split", "status_edit", "event_edit", "reset_lock")


def upgrade() -> None:
    op.create_table(
        "application_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Text(), nullable=False),
        sa.Column("correction_type", sa.Text(), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("correction_type", CORRECTION_TYPES),
            name="ck_application_corrections_correction_type",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_corrections_application_created_at",
        "application_corrections",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_corrections_application_created_at",
        table_name="application_corrections",
    )
    op.drop_table("application_corrections")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"
