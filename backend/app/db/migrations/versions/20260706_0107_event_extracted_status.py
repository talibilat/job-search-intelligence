"""Store extracted status on application events.

Revision ID: 20260706_0107
Revises: 20260705_0084
Create Date: 2026-07-06 10:07:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_0107"
down_revision: str | None = "20260705_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPLICATION_STATUSES = (
    "applied",
    "in_review",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
)


def upgrade() -> None:
    with op.batch_alter_table("application_events") as batch_op:
        batch_op.add_column(sa.Column("extracted_status", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "ck_application_events_extracted_status",
            "extracted_status IS NULL OR " + _in_values("extracted_status", APPLICATION_STATUSES),
        )


def downgrade() -> None:
    with op.batch_alter_table("application_events") as batch_op:
        batch_op.drop_constraint("ck_application_events_extracted_status", type_="check")
        batch_op.drop_column("extracted_status")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"
