"""Create application correction conflict table.

Revision ID: 20260707_0115
Revises: 20260706_0107
Create Date: 2026-07-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0115"
down_revision: str | None = "20260706_0107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONFLICT_TYPES = ("application_summary", "application_event", "ghost_inference")


def upgrade() -> None:
    op.create_table(
        "application_correction_conflicts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Text(), nullable=False),
        sa.Column("conflict_key", sa.Text(), nullable=False),
        sa.Column("conflict_type", sa.Text(), nullable=False),
        sa.Column("existing_json", sa.Text(), nullable=False),
        sa.Column("proposed_json", sa.Text(), nullable=False),
        sa.Column("evidence_email_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("conflict_type", CONFLICT_TYPES),
            name="ck_application_correction_conflicts_type",
        ),
        sa.CheckConstraint(
            "json_valid(existing_json)",
            name="ck_application_correction_conflicts_existing_json_valid",
        ),
        sa.CheckConstraint(
            "json_valid(proposed_json)",
            name="ck_application_correction_conflicts_proposed_json_valid",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_email_id"], ["raw_emails.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conflict_key", name="uq_application_correction_conflicts_key"),
    )
    op.create_index(
        "ix_application_correction_conflicts_application_created_at",
        "application_correction_conflicts",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_correction_conflicts_application_created_at",
        table_name="application_correction_conflicts",
    )
    op.drop_table("application_correction_conflicts")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"
