from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationEventRecord


class EventRepository(BaseRepository[ApplicationEventRecord]):
    """Repository seam for application event timeline records."""

    def upsert_event(
        self,
        *,
        id: str,
        application_id: str,
        event_type: str,
        event_at: str,
        email_id: str | None = None,
        extract_note: str | None = None,
    ) -> None:
        """Insert or update one application event idempotently.

        The deterministic ``id`` (derived from application + event identity
        signals) acts as the conflict target.
        """

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                """
                INSERT INTO application_events (
                    id, application_id, email_id,
                    event_type, event_at, extract_note
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    event_type = excluded.event_type,
                    event_at = excluded.event_at,
                    extract_note = excluded.extract_note
                """,
                (
                    id,
                    application_id,
                    email_id,
                    event_type,
                    event_at,
                    extract_note,
                ),
            )
        if should_commit:
            self.connection.commit()

    def map_row(self, row: sqlite3.Row) -> ApplicationEventRecord:
        return ApplicationEventRecord.model_validate(row_to_dict(row))
