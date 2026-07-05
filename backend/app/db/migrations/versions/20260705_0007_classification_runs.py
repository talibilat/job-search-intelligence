"""Create classification run accounting table.

Revision ID: 20260705_0007
Revises: 20260705_0006
Create Date: 2026-07-05 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0007"
down_revision: str | None = "20260705_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classification_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("classified_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 6), nullable=False),
        sa.CheckConstraint("candidate_count >= 0", name="ck_classification_runs_candidate_count"),
        sa.CheckConstraint("classified_count >= 0", name="ck_classification_runs_classified_count"),
        sa.CheckConstraint(
            "classified_count <= candidate_count",
            name="ck_classification_runs_classified_within_candidates",
        ),
        sa.CheckConstraint("prompt_tokens >= 0", name="ck_classification_runs_prompt_tokens"),
        sa.CheckConstraint(
            "completion_tokens >= 0",
            name="ck_classification_runs_completion_tokens",
        ),
        sa.CheckConstraint("total_tokens >= 0", name="ck_classification_runs_total_tokens"),
        sa.CheckConstraint(
            "total_tokens >= prompt_tokens + completion_tokens",
            name="ck_classification_runs_total_covers_parts",
        ),
        sa.CheckConstraint(
            "estimated_cost_usd >= 0",
            name="ck_classification_runs_estimated_cost_usd",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_classification_runs_started_at",
        "classification_runs",
        ["started_at"],
    )
    op.create_index(
        "ix_classification_runs_provider_model",
        "classification_runs",
        ["provider", "model"],
    )


def downgrade() -> None:
    op.drop_index("ix_classification_runs_provider_model", table_name="classification_runs")
    op.drop_index("ix_classification_runs_started_at", table_name="classification_runs")
    op.drop_table("classification_runs")
