"""Create email connections table.

Revision ID: 20260705_0004
Revises: 20260705_0003
Create Date: 2026-07-05 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0004"
down_revision: str | None = "20260705_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_connections",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("display_email", sa.Text(), nullable=True),
        sa.Column("credential_ref_kind", sa.Text(), nullable=False),
        sa.Column("credential_ref_provider", sa.Text(), nullable=False),
        sa.Column("credential_ref_name", sa.Text(), nullable=False),
        sa.Column("granted_scopes", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.Text(), nullable=False),
        sa.Column("credential_expires_at", sa.Text(), nullable=True),
        sa.Column("reauth_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("provider", "account_id"),
    )
    op.create_index("ix_email_connections_provider", "email_connections", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_email_connections_provider", table_name="email_connections")
    op.drop_table("email_connections")
