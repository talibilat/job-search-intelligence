"""Persist completed interview preparation tasks.

Revision ID: 20260715_0240
Revises: 20260715_0235
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0240"
down_revision: str | None = "20260715_0235"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_task_completions",
        sa.Column("interview_event_id", sa.Text(), nullable=False),
        sa.Column("application_id", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["interview_event_id"],
            ["application_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("interview_event_id"),
    )
    op.create_index(
        "ix_interview_task_completions_application",
        "interview_task_completions",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_task_completions_application",
        table_name="interview_task_completions",
    )
    op.drop_table("interview_task_completions")
