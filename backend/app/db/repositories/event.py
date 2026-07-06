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
        return self.list_for_application(application_id)

    def list_for_application(self, application_id: str) -> list[ApplicationEventRecord]:
        return self.fetch_all(
            """
            SELECT *
            FROM application_events
            WHERE application_id = ?
            ORDER BY event_at, id
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
