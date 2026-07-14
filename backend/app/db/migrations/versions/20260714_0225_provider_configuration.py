"""Add singleton provider configuration.

Revision ID: 20260714_0225
Revises: 20260712_0202
Create Date: 2026-07-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0225"
down_revision: str | None = "20260712_0202"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_configuration",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("email_provider", sa.String(length=32), nullable=False),
        sa.Column("llm_provider", sa.String(length=32), nullable=False),
        sa.Column("classification_mode", sa.String(length=16), nullable=False),
        sa.Column("sync_on_open", sa.Boolean(), nullable=False),
        sa.Column("sync_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("azure_openai_endpoint", sa.Text(), nullable=False),
        sa.Column("azure_openai_api_version", sa.Text(), nullable=False),
        sa.Column("azure_openai_chat_deployment", sa.Text(), nullable=False),
        sa.Column("azure_openai_embedding_deployment", sa.Text(), nullable=False),
        sa.Column("ollama_base_url", sa.Text(), nullable=False),
        sa.Column("ollama_chat_model", sa.Text(), nullable=False),
        sa.Column("ollama_embedding_model", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("singleton_id = 1", name="ck_provider_configuration_singleton"),
        sa.CheckConstraint("email_provider = 'gmail'", name="ck_provider_configuration_email"),
        sa.CheckConstraint(
            "llm_provider IN ('azure_openai', 'ollama')",
            name="ck_provider_configuration_llm",
        ),
        sa.CheckConstraint(
            "classification_mode IN ('hybrid', 'llm', 'local')",
            name="ck_provider_configuration_mode",
        ),
        sa.CheckConstraint(
            "sync_interval_seconds BETWEEN 60 AND 86400",
            name="ck_provider_configuration_sync_interval",
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_configuration")
