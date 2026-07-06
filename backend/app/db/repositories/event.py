from __future__ import annotations

import sqlite3
from typing import Literal

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationEventRecord

type EventUpsertOutcome = Literal["upserted", "locked_unchanged", "manual_conflict"]


class EventRepository(BaseRepository[ApplicationEventRecord]):
    """Repository seam for application event timeline records."""

    def get_by_application_and_id(
        self,
        *,
        application_id: str,
        event_id: str,
    ) -> ApplicationEventRecord | None:
        return self.fetch_one(
            """
            SELECT *
            FROM application_events
            WHERE application_id = ?
              AND id = ?
            """,
            (application_id, event_id),
        )

    def list_by_application_id(
        self,
        application_id: str,
    ) -> list[ApplicationEventRecord]:
        """Return the persisted timeline for one application in event order."""
        return self.list_for_application(application_id)

    def list_for_application(self, application_id: str) -> list[ApplicationEventRecord]:
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

    def list_by_ids_for_application(
        self,
        *,
        application_id: str,
        event_ids: list[str],
    ) -> list[ApplicationEventRecord]:
        if not event_ids:
            return []

        placeholders = ", ".join("?" for _ in event_ids)
        return self.fetch_all(
            f"""
            SELECT *
            FROM application_events
            WHERE application_id = ?
              AND id IN ({placeholders})
            ORDER BY event_at, id
            """,
            (application_id, *event_ids),
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
    ) -> EventUpsertOutcome:
        """Insert or update one application event idempotently.

        The deterministic ``id`` (derived from application + event identity
        signals) acts as the conflict target.
        Events protected by a manual ``event_edit`` correction return
        ``locked_unchanged`` when unchanged or ``manual_conflict`` when new
        evidence disagrees, instead of overwriting the edited timeline row.
        """

        proposed = ApplicationEventRecord.model_validate(
            {
                "id": id,
                "application_id": application_id,
                "email_id": email_id,
                "event_type": event_type,
                "event_at": event_at,
                "extract_note": extract_note,
                "extracted_status": extracted_status,
            }
        )
        existing = self.get_by_application_and_id(
            application_id=application_id,
            event_id=id,
        )
        if existing is not None and self._has_manual_event_edit(
            application_id=application_id,
            event_id=id,
        ):
            if _events_match(existing=existing, proposed=proposed):
                return "locked_unchanged"
            return "manual_conflict"
        if existing is None and self._has_manual_event_edit(
            application_id=application_id,
            event_id=id,
        ):
            return "manual_conflict"
        if existing is None and self._has_manual_event_edit_for_source_email(
            application_id=application_id,
            email_id=email_id,
        ):
            return "manual_conflict"

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
        return "upserted"

    def update_event(
        self,
        *,
        id: str,
        new_id: str,
        application_id: str,
        event_type: str,
        event_at: str,
        email_id: str | None,
        extract_note: str | None,
        extracted_status: str | None,
    ) -> None:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                """
                UPDATE application_events
                SET id = ?,
                    email_id = ?,
                    event_type = ?,
                    event_at = ?,
                    extract_note = ?,
                    extracted_status = ?
                WHERE id = ?
                  AND application_id = ?
                """,
                (
                    new_id,
                    email_id,
                    event_type,
                    event_at,
                    extract_note,
                    extracted_status,
                    id,
                    application_id,
                ),
            )
        if should_commit:
            self.connection.commit()

    def raw_email_exists(self, email_id: str) -> bool:
        row = self.execute(
            "SELECT 1 FROM raw_emails WHERE id = ? LIMIT 1",
            (email_id,),
        ).fetchone()
        return row is not None

    def _has_manual_event_edit_for_source_email(
        self,
        *,
        application_id: str,
        email_id: str | None,
    ) -> bool:
        if email_id is None:
            return False
        row = self.execute(
            """
            SELECT 1
            FROM application_corrections
            WHERE application_id = ?
              AND correction_type = 'event_edit'
              AND (
                json_extract(before_json, '$.event.email_id') = ?
                OR json_extract(after_json, '$.event.email_id') = ?
              )
            LIMIT 1
            """,
            (application_id, email_id, email_id),
        ).fetchone()
        return row is not None

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

    def reassign_events(
        self,
        *,
        event_ids: list[str],
        from_application_id: str,
        to_application_id: str,
    ) -> int:
        """Move existing events from one application timeline to another."""

        if not event_ids:
            return 0

        placeholders = ", ".join("?" for _ in event_ids)
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                f"""
                UPDATE application_events
                SET application_id = ?
                WHERE application_id = ?
                  AND id IN ({placeholders})
                """,
                (to_application_id, from_application_id, *event_ids),
            )
        if should_commit:
            self.connection.commit()
        return cursor.rowcount

    def map_row(self, row: sqlite3.Row) -> ApplicationEventRecord:
        return ApplicationEventRecord.model_validate(row_to_dict(row))

    def _has_manual_event_edit(
        self,
        *,
        application_id: str,
        event_id: str,
    ) -> bool:
        row = self.execute(
            """
            SELECT 1
            FROM application_corrections
            WHERE application_id = ?
              AND correction_type = 'event_edit'
              AND (
                json_extract(before_json, '$.event.id') = ?
                OR json_extract(after_json, '$.event.id') = ?
              )
            LIMIT 1
            """,
            (application_id, event_id, event_id),
        ).fetchone()
        return row is not None


def _events_match(
    *,
    existing: ApplicationEventRecord,
    proposed: ApplicationEventRecord,
) -> bool:
    return (
        existing.email_id == proposed.email_id
        and existing.event_type == proposed.event_type
        and existing.event_at == proposed.event_at
        and existing.extract_note == proposed.extract_note
        and existing.extracted_status == proposed.extracted_status
    )
