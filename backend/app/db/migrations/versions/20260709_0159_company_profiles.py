from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260709_0159"
down_revision = "20260707_0190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("normalized_company", sa.Text(), primary_key=True),
        sa.Column("display_company", sa.Text(), nullable=False),
        sa.Column("company_type", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "company_type IN ('startup', 'enterprise', 'public_company', 'agency', "
            "'nonprofit', 'education', 'government', 'unknown', 'other')",
            name="ck_company_profiles_company_type",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'imported', 'extracted', 'unknown')",
            name="ck_company_profiles_source",
        ),
    )
    op.create_index(
        "ix_company_profiles_company_type",
        "company_profiles",
        ["company_type"],
    )
    op.create_index(
        "ix_company_profiles_industry",
        "company_profiles",
        ["industry"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_profiles_industry", table_name="company_profiles")
    op.drop_index("ix_company_profiles_company_type", table_name="company_profiles")
    op.drop_table("company_profiles")
