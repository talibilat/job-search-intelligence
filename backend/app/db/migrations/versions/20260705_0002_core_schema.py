"""Create core job tracker schema.

Revision ID: 20260705_0002
Revises: 20260705_0001
Create Date: 2026-07-05 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0002"
down_revision: str | None = "20260705_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAW_EMAIL_RETENTION_STATES = ("metadata_only", "retained", "debugging")
CLASSIFICATION_CATEGORIES = (
    "application_confirmation",
    "rejection",
    "interview_invite",
    "recruiter_outreach",
    "offer",
    "assessment",
    "follow_up",
    "other",
)
APPLICATION_SOURCES = ("linkedin", "company_site", "indeed", "referral", "other")
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
WORK_MODES = ("remote", "hybrid", "onsite")
SPONSORSHIP_STATUSES = ("offered", "not_offered", "unknown")
EVENT_TYPES = (
    "applied",
    "response",
    "assessment",
    "interview_scheduled",
    "feedback",
    "rejection",
    "offer",
    "ghost_inferred",
)
INSIGHT_TYPES = (
    "why_rejected",
    "recurring_feedback",
    "skill_gaps",
    "strongest_weakest_signals",
    "role_fit",
    "weekly_actions",
    "story",
)


def upgrade() -> None:
    op.create_table(
        "raw_emails",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column("from_addr", sa.Text(), nullable=True),
        sa.Column("to_addr", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_retention_state", sa.Text(), nullable=False),
        sa.Column("labels", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("body_retention_state", RAW_EMAIL_RETENTION_STATES),
            name="ck_raw_emails_body_retention_state",
        ),
        sa.CheckConstraint(
            "(body_retention_state = 'metadata_only' AND body_text IS NULL) "
            "OR (body_retention_state IN ('retained', 'debugging') AND body_text IS NOT NULL)",
            name="ck_raw_emails_body_text_matches_retention_state",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_emails_provider_sent_at", "raw_emails", ["provider", "sent_at"])
    op.create_index("ix_raw_emails_thread_id", "raw_emails", ["thread_id"])

    op.create_table(
        "email_classifications",
        sa.Column("email_id", sa.Text(), nullable=False),
        sa.Column("is_job_related", sa.Boolean(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("classified_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("category", CLASSIFICATION_CATEGORIES),
            name="ck_email_classifications_category",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_email_classifications_confidence",
        ),
        sa.ForeignKeyConstraint(["email_id"], ["raw_emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("email_id"),
    )
    op.create_index("ix_email_classifications_category", "email_classifications", ["category"])
    op.create_index(
        "ix_email_classifications_is_job_related",
        "email_classifications",
        ["is_job_related"],
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("role_title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.Text(), nullable=False),
        sa.Column("current_status", sa.Text(), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("work_mode", sa.Text(), nullable=True),
        sa.Column("seniority", sa.Text(), nullable=True),
        sa.Column("sponsorship", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("tech_stack", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_activity_at", sa.Text(), nullable=False),
        sa.Column("manual_lock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in_values("source", APPLICATION_SOURCES),
            name="ck_applications_source",
        ),
        sa.CheckConstraint(
            _in_values("current_status", APPLICATION_STATUSES),
            name="ck_applications_current_status",
        ),
        sa.CheckConstraint(
            "work_mode IS NULL OR " + _in_values("work_mode", WORK_MODES),
            name="ck_applications_work_mode",
        ),
        sa.CheckConstraint(
            _in_values("sponsorship", SPONSORSHIP_STATUSES),
            name="ck_applications_sponsorship",
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_min >= 0",
            name="ck_applications_salary_min",
        ),
        sa.CheckConstraint(
            "salary_max IS NULL OR salary_max >= 0",
            name="ck_applications_salary_max",
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min",
            name="ck_applications_salary_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_current_status", "applications", ["current_status"])
    op.create_index("ix_applications_first_seen_at", "applications", ["first_seen_at"])
    op.create_index("ix_applications_source", "applications", ["source"])

    op.create_table(
        "application_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("application_id", sa.Text(), nullable=False),
        sa.Column("email_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_at", sa.Text(), nullable=False),
        sa.Column("extract_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _in_values("event_type", EVENT_TYPES),
            name="ck_application_events_event_type",
        ),
        sa.CheckConstraint(
            "(event_type = 'ghost_inferred' AND email_id IS NULL) OR "
            "(event_type != 'ghost_inferred' AND email_id IS NOT NULL)",
            name="ck_application_events_email_required_for_evidence_events",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["raw_emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_events_application_event_at",
        "application_events",
        ["application_id", "event_at"],
    )
    op.create_index("ix_application_events_email_id", "application_events", ["email_id"])

    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("inputs_hash", sa.Text(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(_in_values("type", INSIGHT_TYPES), name="ck_insights_type"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insights_inputs_hash", "insights", ["inputs_hash"])
    op.create_index("ix_insights_type", "insights", ["type"])

    op.execute(
        "CREATE VIRTUAL TABLE email_chunks USING vec0("
        "email_id TEXT, "
        "chunk_index INTEGER, "
        "+content TEXT, "
        "embedding float[1536]"
        ")",
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_chunks")
    op.drop_index("ix_insights_type", table_name="insights")
    op.drop_index("ix_insights_inputs_hash", table_name="insights")
    op.drop_table("insights")
    op.drop_index("ix_application_events_email_id", table_name="application_events")
    op.drop_index("ix_application_events_application_event_at", table_name="application_events")
    op.drop_table("application_events")
    op.drop_index("ix_applications_source", table_name="applications")
    op.drop_index("ix_applications_first_seen_at", table_name="applications")
    op.drop_index("ix_applications_current_status", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_email_classifications_is_job_related", table_name="email_classifications")
    op.drop_index("ix_email_classifications_category", table_name="email_classifications")
    op.drop_table("email_classifications")
    op.drop_index("ix_raw_emails_thread_id", table_name="raw_emails")
    op.drop_index("ix_raw_emails_provider_sent_at", table_name="raw_emails")
    op.drop_table("raw_emails")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"
