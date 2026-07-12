from __future__ import annotations

import sqlite3
from datetime import datetime

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import EmailSyncStateRecord
from app.providers.email import EmailAccountRef, EmailProviderCursor, EmailSyncMode


class SyncStateRepository(BaseRepository[EmailSyncStateRecord]):
    """Persist provider-owned email sync anchors for resumable ingestion."""

    def save_cursor(
        self,
        cursor: EmailProviderCursor,
        *,
        updated_at: datetime,
    ) -> EmailSyncStateRecord:
        should_commit = not self.connection.in_transaction

        with self.transaction():
            self.execute(
                """
                INSERT INTO email_sync_state (
                    provider,
                    account_id,
                    sync_cursor,
                    cursor_issued_at,
                    in_progress_mode,
                    next_page_token,
                    updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?)
                ON CONFLICT(provider, account_id) DO UPDATE SET
                    sync_cursor = excluded.sync_cursor,
                    cursor_issued_at = excluded.cursor_issued_at,
                    in_progress_mode = NULL,
                    next_page_token = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    cursor.account.provider.value,
                    cursor.account.account_id,
                    cursor.value,
                    cursor.issued_at.isoformat(),
                    updated_at.isoformat(),
                ),
            )

        if should_commit:
            self.connection.commit()

        record = self.fetch_state(cursor.account)
        if record is None:
            msg = "stored sync cursor could not be read back"
            raise RuntimeError(msg)
        return record

    def save_page_progress(
        self,
        account: EmailAccountRef,
        *,
        mode: EmailSyncMode,
        next_page_token: str,
        sync_cursor: EmailProviderCursor | None,
        updated_at: datetime,
    ) -> EmailSyncStateRecord:
        should_commit = not self.connection.in_transaction

        with self.transaction():
            self.execute(
                """
                INSERT INTO email_sync_state (
                    provider,
                    account_id,
                    sync_cursor,
                    cursor_issued_at,
                    in_progress_mode,
                    next_page_token,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, account_id) DO UPDATE SET
                    sync_cursor = excluded.sync_cursor,
                    cursor_issued_at = excluded.cursor_issued_at,
                    in_progress_mode = excluded.in_progress_mode,
                    next_page_token = excluded.next_page_token,
                    updated_at = excluded.updated_at
                """,
                (
                    account.provider.value,
                    account.account_id,
                    sync_cursor.value if sync_cursor is not None else None,
                    sync_cursor.issued_at.isoformat() if sync_cursor is not None else None,
                    mode.value,
                    next_page_token,
                    updated_at.isoformat(),
                ),
            )

        if should_commit:
            self.connection.commit()

        record = self.fetch_state(account)
        if record is None:
            msg = "stored sync progress could not be read back"
            raise RuntimeError(msg)
        return record

    def clear_page_progress(
        self,
        account: EmailAccountRef,
        *,
        updated_at: datetime,
    ) -> EmailSyncStateRecord | None:
        should_commit = not self.connection.in_transaction

        with self.transaction():
            self.execute(
                """
                UPDATE email_sync_state
                SET
                    in_progress_mode = NULL,
                    next_page_token = NULL,
                    updated_at = ?
                WHERE provider = ? AND account_id = ?
                """,
                (updated_at.isoformat(), account.provider.value, account.account_id),
            )

        if should_commit:
            self.connection.commit()

        return self.fetch_state(account)

    def fetch_state(self, account: EmailAccountRef) -> EmailSyncStateRecord | None:
        return self.fetch_one(
            """
            SELECT
                provider,
                account_id,
                sync_cursor,
                cursor_issued_at,
                in_progress_mode,
                next_page_token,
                updated_at
            FROM email_sync_state
            WHERE provider = ? AND account_id = ?
            """,
            (account.provider.value, account.account_id),
        )

    def get_cursor(self, account: EmailAccountRef) -> EmailProviderCursor | None:
        state = self.fetch_state(account)
        if state is None:
            return None
        if state.sync_cursor is None or state.cursor_issued_at is None:
            return None

        return EmailProviderCursor(
            account=EmailAccountRef(
                provider=EmailProviderName(state.provider),
                account_id=state.account_id,
            ),
            value=state.sync_cursor,
            issued_at=state.cursor_issued_at,
        )

    def latest_update_at(self) -> datetime | None:
        row = self.connection.execute("SELECT MAX(updated_at) FROM email_sync_state").fetchone()
        return None if row is None or row[0] is None else datetime.fromisoformat(row[0])

    def map_row(self, row: sqlite3.Row) -> EmailSyncStateRecord:
        return EmailSyncStateRecord.model_validate(row_to_dict(row))
