"""Add non-secret Tavily web search configuration.

Revision ID: 20260718_0247
Revises: 20260718_0246
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0247"
down_revision: str | None = "20260718_0246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_configuration") as batch_op:
        batch_op.add_column(
            sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column(
                "web_search_provider",
                sa.String(length=32),
                nullable=False,
                server_default="tavily",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tavily_base_url",
                sa.Text(),
                nullable=False,
                server_default="https://api.tavily.com",
            )
        )
        batch_op.add_column(
            sa.Column("web_search_max_results", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.add_column(
            sa.Column(
                "web_search_timeout_seconds", sa.Integer(), nullable=False, server_default="10"
            )
        )
        batch_op.create_check_constraint(
            "ck_provider_configuration_web_search_provider",
            "web_search_provider = 'tavily'",
        )
        batch_op.create_check_constraint(
            "ck_provider_configuration_web_search_max_results",
            "web_search_max_results BETWEEN 1 AND 10",
        )
        batch_op.create_check_constraint(
            "ck_provider_configuration_web_search_timeout",
            "web_search_timeout_seconds BETWEEN 1 AND 120",
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_configuration") as batch_op:
        batch_op.drop_constraint("ck_provider_configuration_web_search_timeout", type_="check")
        batch_op.drop_constraint("ck_provider_configuration_web_search_max_results", type_="check")
        batch_op.drop_constraint("ck_provider_configuration_web_search_provider", type_="check")
        batch_op.drop_column("web_search_timeout_seconds")
        batch_op.drop_column("web_search_max_results")
        batch_op.drop_column("tavily_base_url")
        batch_op.drop_column("web_search_provider")
        batch_op.drop_column("web_search_enabled")
