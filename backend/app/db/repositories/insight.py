from __future__ import annotations

import sqlite3
from datetime import datetime

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import InsightRecord, InsightType


class InsightRepository(BaseRepository[InsightRecord]):
    """Repository seam for cached narrative insights."""

    def save_generated_insight(
        self,
        *,
        insight_type: InsightType,
        content: str,
        inputs_hash: str,
        model: str,
        generated_at: datetime,
    ) -> InsightRecord:
        existing = self.get_latest_insight(insight_type, include_stale=True)
        should_commit = not self.connection.in_transaction
        with self.transaction():
            if existing is None:
                cursor = self.execute(
                    """
                    INSERT INTO insights (
                        type,
                        content,
                        inputs_hash,
                        is_stale,
                        model,
                        generated_at
                    ) VALUES (?, ?, ?, 0, ?, ?)
                    """,
                    (
                        insight_type,
                        content,
                        inputs_hash,
                        model,
                        _format_datetime(generated_at),
                    ),
                )
                insight_id = cursor.lastrowid
            else:
                insight_id = existing.id
                self.execute(
                    """
                    UPDATE insights
                    SET content = ?,
                        inputs_hash = ?,
                        is_stale = 0,
                        model = ?,
                        generated_at = ?
                    WHERE id = ?
                    """,
                    (
                        content,
                        inputs_hash,
                        model,
                        _format_datetime(generated_at),
                        insight_id,
                    ),
                )

            row = self.execute("SELECT * FROM insights WHERE id = ?", (insight_id,)).fetchone()

        if should_commit:
            self.connection.commit()
        if row is None:
            msg = "saved insight row was not found"
            raise RuntimeError(msg)
        return self.map_row(row)

    def fetch_insight(self, insight_id: int) -> InsightRecord | None:
        return self.fetch_one("SELECT * FROM insights WHERE id = ?", (insight_id,))

    def get_cached_insight(
        self,
        *,
        insight_type: InsightType,
        inputs_hash: str,
        model: str,
    ) -> InsightRecord | None:
        return self.fetch_one(
            """
            SELECT *
            FROM insights
            WHERE type = ?
              AND inputs_hash = ?
              AND model = ?
              AND is_stale = 0
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (insight_type, inputs_hash, model),
        )

    def get_latest_insight(
        self,
        insight_type: InsightType,
        *,
        include_stale: bool = False,
    ) -> InsightRecord | None:
        stale_clause = "" if include_stale else "AND is_stale = 0"
        return self.fetch_one(
            f"""
            SELECT *
            FROM insights
            WHERE type = ?
              {stale_clause}
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (insight_type,),
        )

    def mark_stale_except_inputs_hash(self, inputs_hash: str) -> int:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                """
                UPDATE insights
                SET is_stale = 1
                WHERE inputs_hash != ?
                  AND is_stale = 0
                """,
                (inputs_hash,),
            )

        if should_commit:
            self.connection.commit()
        return cursor.rowcount

    def map_row(self, row: sqlite3.Row) -> InsightRecord:
        return InsightRecord.model_validate(row_to_dict(row))


def _format_datetime(value: datetime) -> str:
    return value.isoformat()
