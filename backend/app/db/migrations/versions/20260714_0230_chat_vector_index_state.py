"""Track the configured provider identity for persisted email vectors.

Revision ID: 20260714_0230
Revises: 20260714_0225
Create Date: 2026-07-14 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0230"
down_revision: str | None = "20260714_0225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_chunk_index_state",
        sa.Column("email_id", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["raw_emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("email_id"),
    )
    op.create_index(
        "ix_email_chunk_index_state_provider_model",
        "email_chunk_index_state",
        ["provider", "model"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_chunk_index_state_provider_model",
        table_name="email_chunk_index_state",
    )
    op.drop_table("email_chunk_index_state")
