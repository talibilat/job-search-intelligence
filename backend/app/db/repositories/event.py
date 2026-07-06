from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationEventRecord


class EventRepository(BaseRepository[ApplicationEventRecord]):
    """Repository seam for application event timeline records."""

    def list_by_application_id(
        self,
        application_id: str,
    ) -> list[ApplicationEventRecord]:
        """Return the persisted timeline for one application in event order."""

        return self.fetch_all(
            """
            SELECT
                application_events.*,
                raw_emails.sent_at AS email_sent_at,
                email_classifications.classified_at AS classification_classified_at
            FROM application_events
            LEFT JOIN raw_emails
                ON raw_emails.id = application_events.email_id
            LEFT JOIN email_classifications
                ON email_classifications.email_id = application_events.email_id
            WHERE application_id = ?
            ORDER BY
                application_events.event_at,
                raw_emails.sent_at,
                email_classifications.classified_at,
                application_events.id
            """,
            (application_id,),
        )

    def upsert_event(
        self,
        *,
        id: str,
        application_id: str,
        event_type: str,
        event_at: str,
        email_id: str | None = None,
        extract_note: str | None = None,
        extracted_status: str | None = None,
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
                    event_type, event_at, extract_note, extracted_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    event_type = excluded.event_type,
                    event_at = excluded.event_at,
                    extract_note = excluded.extract_note,
                    extracted_status = excluded.extracted_status
                """,
                (
                    id,
                    application_id,
                    email_id,
                    event_type,
                    event_at,
                    extract_note,
                    extracted_status,
                ),
            )
        if should_commit:
            self.connection.commit()

    def reassign_application_events(
        self,
        *,
        source_application_id: str,
        target_application_id: str,
    ) -> int:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                """
                UPDATE application_events
                SET application_id = ?
                WHERE application_id = ?
                """,
                (target_application_id, source_application_id),
            )
        if should_commit:
            self.connection.commit()
        return cursor.rowcount

    def map_row(self, row: sqlite3.Row) -> ApplicationEventRecord:
        return ApplicationEventRecord.model_validate(row_to_dict(row))
