from __future__ import annotations

import sqlite3
from datetime import datetime

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import EmailBackfillStateRecord
from app.providers.email import EmailAccountRef


class BackfillStateRepository(BaseRepository[EmailBackfillStateRecord]):
    """Persist full metadata backfill progress for resumable ingestion."""

    def save_state(self, state: EmailBackfillStateRecord) -> EmailBackfillStateRecord:
        should_commit = not self.connection.in_transaction

        with self.transaction():
            self.execute(
                """
                INSERT INTO email_backfill_state (
                    provider,
                    account_id,
                    status,
                    next_page_token,
                    processed_page_count,
                    processed_message_count,
                    sync_cursor,
                    cursor_issued_at,
                    started_at,
                    updated_at,
                    completed_at,
                    last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, account_id) DO UPDATE SET
                    status = excluded.status,
                    next_page_token = excluded.next_page_token,
                    processed_page_count = excluded.processed_page_count,
                    processed_message_count = excluded.processed_message_count,
                    sync_cursor = excluded.sync_cursor,
                    cursor_issued_at = excluded.cursor_issued_at,
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at,
                    completed_at = excluded.completed_at,
                    last_error = excluded.last_error
                """,
                (
                    state.provider,
                    state.account_id,
                    state.status.value,
                    state.next_page_token,
                    state.processed_page_count,
                    state.processed_message_count,
                    state.sync_cursor,
                    state.cursor_issued_at.isoformat() if state.cursor_issued_at else None,
                    state.started_at.isoformat(),
                    state.updated_at.isoformat(),
                    state.completed_at.isoformat() if state.completed_at else None,
                    state.last_error,
                ),
            )

        if should_commit:
            self.connection.commit()

        record = self.fetch_state(
            EmailAccountRef.model_validate(
                {
                    "provider": state.provider,
                    "account_id": state.account_id,
                }
            )
        )
        if record is None:
            msg = "stored backfill state could not be read back"
            raise RuntimeError(msg)
        return record

    def fetch_state(self, account: EmailAccountRef) -> EmailBackfillStateRecord | None:
        return self.fetch_one(
            """
            SELECT
                provider,
                account_id,
                status,
                next_page_token,
                processed_page_count,
                processed_message_count,
                sync_cursor,
                cursor_issued_at,
                started_at,
                updated_at,
                completed_at,
                last_error
            FROM email_backfill_state
            WHERE provider = ? AND account_id = ?
            """,
            (account.provider.value, account.account_id),
        )

    def latest_completed_at(self) -> datetime | None:
        row = self.connection.execute(
            "SELECT MAX(completed_at) FROM email_backfill_state WHERE completed_at IS NOT NULL"
        ).fetchone()
        return None if row is None or row[0] is None else datetime.fromisoformat(row[0])

    def map_row(self, row: sqlite3.Row) -> EmailBackfillStateRecord:
        return EmailBackfillStateRecord.model_validate(row_to_dict(row))
