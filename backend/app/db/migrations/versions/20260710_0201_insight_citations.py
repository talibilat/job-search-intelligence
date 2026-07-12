"""Add persisted evidence citations to cached insights.

Revision ID: 20260710_0201
Revises: 20260709_0159
Create Date: 2026-07-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0201"
down_revision: str | None = "20260709_0159"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    trigger_sql = _drop_staleness_triggers()
    with op.batch_alter_table("insights") as batch_op:
        batch_op.add_column(
            sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"),
        )
    _restore_staleness_triggers(trigger_sql)


def downgrade() -> None:
    trigger_sql = _drop_staleness_triggers()
    with op.batch_alter_table("insights") as batch_op:
        batch_op.drop_column("citations_json")
    _restore_staleness_triggers(trigger_sql)


def _drop_staleness_triggers() -> tuple[str, ...]:
    connection = op.get_bind()
    placeholders = ", ".join(f":name_{index}" for index in range(len(TRIGGER_NAMES)))
    parameters = {f"name_{index}": name for index, name in enumerate(TRIGGER_NAMES)}
    rows = connection.execute(
        sa.text(
            "SELECT sql FROM sqlite_master "
            f"WHERE type = 'trigger' AND name IN ({placeholders}) ORDER BY name"
        ),
        parameters,
    )
    trigger_sql = tuple(row[0] for row in rows if row[0])
    for trigger_name in TRIGGER_NAMES:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    return trigger_sql


def _restore_staleness_triggers(trigger_sql: tuple[str, ...]) -> None:
    for statement in trigger_sql:
        op.execute(statement)
