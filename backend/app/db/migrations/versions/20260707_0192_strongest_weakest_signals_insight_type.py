"""Add strongest and weakest signals insight type.

Revision ID: 20260707_0192
Revises: 20260707_0183
Create Date: 2026-07-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0192"
down_revision: str | None = "20260707_0183"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INSIGHT_TYPES = (
    "why_rejected",
    "skill_gaps",
    "strongest_weakest_signals",
    "role_fit",
    "weekly_actions",
    "story",
)
DOWNGRADE_INSIGHT_TYPES = (
    "why_rejected",
    "skill_gaps",
    "role_fit",
    "weekly_actions",
    "story",
)
TRIGGER_NAMES = (
    "trg_insights_stale_after_applications_insert",
    "trg_insights_stale_after_applications_update",
    "trg_insights_stale_after_applications_delete",
    "trg_insights_stale_after_application_events_insert",
    "trg_insights_stale_after_application_events_update",
    "trg_insights_stale_after_application_events_delete",
    "trg_insights_stale_after_raw_emails_insert",
    "trg_insights_stale_after_raw_emails_update",
    "trg_insights_stale_after_raw_emails_delete",
)


def upgrade() -> None:
    _drop_insight_staleness_triggers()
    _replace_insight_type_constraint(INSIGHT_TYPES)
    _create_insight_staleness_triggers()


def downgrade() -> None:
    _drop_insight_staleness_triggers()
    op.execute("DELETE FROM insights WHERE type = 'strongest_weakest_signals'")
    _replace_insight_type_constraint(DOWNGRADE_INSIGHT_TYPES)
    _create_insight_staleness_triggers()


def _drop_insight_staleness_triggers() -> None:
    for trigger_name in TRIGGER_NAMES:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")


def _create_insight_staleness_triggers() -> None:
    for trigger_sql in _insight_staleness_trigger_sql():
        op.execute(trigger_sql)


def _replace_insight_type_constraint(values: Sequence[str]) -> None:
    with op.batch_alter_table(
        "insights",
        recreate="always",
        table_args=(sa.CheckConstraint(_in_values("type", values), name="ck_insights_type"),),
    ) as batch_op:
        batch_op.drop_constraint("ck_insights_type", type_="check")


def _in_values(column_name: str, values: Sequence[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def _insight_staleness_trigger_sql() -> tuple[str, ...]:
    return (
        """
        CREATE TRIGGER trg_insights_stale_after_applications_insert
        AFTER INSERT ON applications
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_applications_update
        AFTER UPDATE ON applications
        WHEN OLD.id IS NOT NEW.id
          OR OLD.company IS NOT NEW.company
          OR OLD.role_title IS NOT NEW.role_title
          OR OLD.source IS NOT NEW.source
          OR OLD.first_seen_at IS NOT NEW.first_seen_at
          OR OLD.current_status IS NOT NEW.current_status
          OR OLD.salary_min IS NOT NEW.salary_min
          OR OLD.salary_max IS NOT NEW.salary_max
          OR OLD.currency IS NOT NEW.currency
          OR OLD.location IS NOT NEW.location
          OR OLD.work_mode IS NOT NEW.work_mode
          OR OLD.seniority IS NOT NEW.seniority
          OR OLD.sponsorship IS NOT NEW.sponsorship
          OR OLD.tech_stack IS NOT NEW.tech_stack
          OR OLD.last_activity_at IS NOT NEW.last_activity_at
          OR OLD.manual_lock IS NOT NEW.manual_lock
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_applications_delete
        AFTER DELETE ON applications
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_application_events_insert
        AFTER INSERT ON application_events
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_application_events_update
        AFTER UPDATE ON application_events
        WHEN OLD.id IS NOT NEW.id
          OR OLD.application_id IS NOT NEW.application_id
          OR OLD.email_id IS NOT NEW.email_id
          OR OLD.event_type IS NOT NEW.event_type
          OR OLD.event_at IS NOT NEW.event_at
          OR OLD.extract_note IS NOT NEW.extract_note
          OR OLD.extracted_status IS NOT NEW.extracted_status
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_application_events_delete
        AFTER DELETE ON application_events
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_raw_emails_insert
        AFTER INSERT ON raw_emails
        WHEN EXISTS (
            SELECT 1
            FROM application_events
            WHERE application_events.email_id = NEW.id
        )
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_raw_emails_update
        AFTER UPDATE ON raw_emails
        WHEN (
            OLD.id IS NOT NEW.id
            OR OLD.from_addr IS NOT NEW.from_addr
            OR OLD.subject IS NOT NEW.subject
            OR OLD.sent_at IS NOT NEW.sent_at
            OR OLD.body_text IS NOT NEW.body_text
            OR OLD.body_retention_state IS NOT NEW.body_retention_state
        )
        AND (
            EXISTS (
                SELECT 1
                FROM application_events
                WHERE application_events.email_id = OLD.id
            )
            OR EXISTS (
                SELECT 1
                FROM application_events
                WHERE application_events.email_id = NEW.id
            )
        )
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
        """
        CREATE TRIGGER trg_insights_stale_after_raw_emails_delete
        AFTER DELETE ON raw_emails
        WHEN EXISTS (
            SELECT 1
            FROM application_events
            WHERE application_events.email_id = OLD.id
        )
        BEGIN
            UPDATE insights
            SET is_stale = 1
            WHERE is_stale = 0;
        END
        """,
    )
