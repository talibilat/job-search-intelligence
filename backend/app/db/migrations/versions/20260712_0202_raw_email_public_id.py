"""Add opaque public identifiers to raw emails.

Revision ID: 20260712_0202
Revises: 20260710_0201
Create Date: 2026-07-12 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_0202"
down_revision: str | None = "20260710_0201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The schema owns identifier generation so every insert path, present or
# future, produces a row that satisfies the non-null DTO contract.
PUBLIC_ID_DEFAULT = sa.text("(lower(hex(randomblob(16))))")

# Batch mode rebuilds raw_emails, which drops triggers defined on it; they
# must be captured and restored around the rebuild in both directions.
TRIGGER_NAMES = (
    "trg_insights_stale_after_raw_emails_insert",
    "trg_insights_stale_after_raw_emails_update",
    "trg_insights_stale_after_raw_emails_delete",
)


def upgrade() -> None:
    trigger_sql = _drop_raw_email_triggers()
    with op.batch_alter_table("raw_emails") as batch_op:
        batch_op.add_column(
            sa.Column(
                "public_id",
                sa.String(length=32),
                nullable=False,
                server_default=PUBLIC_ID_DEFAULT,
            )
        )
    op.create_index(
        "ux_raw_emails_public_id",
        "raw_emails",
        ["public_id"],
        unique=True,
    )
    _restore_raw_email_triggers(trigger_sql)


def downgrade() -> None:
    trigger_sql = _drop_raw_email_triggers()
    op.drop_index("ux_raw_emails_public_id", table_name="raw_emails")
    with op.batch_alter_table("raw_emails") as batch_op:
        batch_op.drop_column("public_id")
    _restore_raw_email_triggers(trigger_sql)


def _drop_raw_email_triggers() -> tuple[str, ...]:
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


def _restore_raw_email_triggers(trigger_sql: tuple[str, ...]) -> None:
    for statement in trigger_sql:
        op.execute(statement)
