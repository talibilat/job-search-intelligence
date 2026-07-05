from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import EmailFilterDecisionRecord


class EmailFilterDecisionRepository(BaseRepository[EmailFilterDecisionRecord]):
    """Repository seam for persisted heuristic filter audit decisions."""

    def upsert_filter_decisions(self, records: Iterable[EmailFilterDecisionRecord]) -> int:
        record_tuple = tuple(records)
        if not record_tuple:
            return 0

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute_many(
                """
                INSERT INTO email_filter_decisions (
                    email_id,
                    strategy,
                    outcome,
                    reason,
                    decided_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(email_id, strategy) DO UPDATE SET
                    outcome = excluded.outcome,
                    reason = excluded.reason,
                    decided_at = excluded.decided_at
                """,
                [
                    (
                        record.email_id,
                        record.strategy.value,
                        record.outcome.value,
                        record.reason,
                        record.decided_at.isoformat(),
                    )
                    for record in record_tuple
                ],
            )

        if should_commit:
            self.connection.commit()
        return len(record_tuple)

    def map_row(self, row: sqlite3.Row) -> EmailFilterDecisionRecord:
        return EmailFilterDecisionRecord.model_validate(row_to_dict(row))
