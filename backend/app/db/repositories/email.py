from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import RawEmailRecord


class EmailRepository(BaseRepository[RawEmailRecord]):
    """Repository seam for raw email records with typed retention validation."""

    def upsert_raw_emails(self, records: Iterable[RawEmailRecord]) -> None:
        """Write raw email rows idempotently by provider message ID."""

        record_tuple = tuple(records)
        if not record_tuple:
            return

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute_many(
                """
                INSERT INTO raw_emails (
                    id,
                    thread_id,
                    from_addr,
                    to_addr,
                    subject,
                    sent_at,
                    body_text,
                    body_retention_state,
                    labels,
                    provider,
                    ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    from_addr = excluded.from_addr,
                    to_addr = excluded.to_addr,
                    subject = excluded.subject,
                    sent_at = excluded.sent_at,
                    body_text = excluded.body_text,
                    body_retention_state = excluded.body_retention_state,
                    labels = excluded.labels,
                    provider = excluded.provider,
                    ingested_at = excluded.ingested_at
                """,
                [
                    (
                        record.id,
                        record.thread_id,
                        record.from_addr,
                        record.to_addr,
                        record.subject,
                        record.sent_at.isoformat() if record.sent_at is not None else None,
                        record.body_text,
                        record.body_retention_state.value,
                        json.dumps(record.labels, separators=(",", ":")),
                        record.provider,
                        record.ingested_at.isoformat(),
                    )
                    for record in record_tuple
                ],
            )

        if should_commit:
            self.connection.commit()

    def count_raw_emails(self, *, provider: EmailProviderName | None = None) -> int:
        if provider is None:
            row = self.execute("SELECT COUNT(*) FROM raw_emails").fetchone()
        else:
            row = self.execute(
                "SELECT COUNT(*) FROM raw_emails WHERE provider = ?",
                (provider.value,),
            ).fetchone()

        if row is None:
            return 0
        return int(row[0])

    def list_raw_email_ids(self, *, provider: EmailProviderName) -> list[str]:
        rows = self.execute(
            "SELECT id FROM raw_emails WHERE provider = ? ORDER BY id",
            (provider.value,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def map_row(self, row: sqlite3.Row) -> RawEmailRecord:
        return RawEmailRecord.model_validate(row_to_dict(row))
