"""Persist short-lived OAuth authorization state across local backend reloads.

Revision ID: 20260715_0235
Revises: 20260714_0230
"""

import sqlalchemy as sa
from alembic import op

revision = "20260715_0235"
down_revision = "20260714_0230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_authorization_states",
        sa.Column("state_hash", sa.String(length=64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_oauth_authorization_states_expires_at",
        "oauth_authorization_states",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_authorization_states_expires_at")
    op.drop_table("oauth_authorization_states")
