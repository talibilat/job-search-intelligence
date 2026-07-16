from __future__ import annotations

import sqlite3
from datetime import datetime

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ClassificationRunRecord


class ClassificationRunRepository(BaseRepository[ClassificationRunRecord]):
    """Repository for per-run classification token and cost accounting."""

    def upsert_run(self, record: ClassificationRunRecord) -> None:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                """
                INSERT INTO classification_runs (
                    id,
                    provider,
                    model,
                    prompt_version,
                    started_at,
                    completed_at,
                    candidate_count,
                    classified_count,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    candidate_count = excluded.candidate_count,
                    classified_count = excluded.classified_count,
                    prompt_tokens = excluded.prompt_tokens,
                    completion_tokens = excluded.completion_tokens,
                    total_tokens = excluded.total_tokens,
                    estimated_cost_usd = excluded.estimated_cost_usd
                """,
                (
                    record.id,
                    record.provider,
                    record.model,
                    record.prompt_version,
                    _format_datetime(record.started_at),
                    _format_datetime(record.completed_at),
                    record.candidate_count,
                    record.classified_count,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    format(record.estimated_cost_usd, "f"),
                ),
            )

        if should_commit:
            self.connection.commit()

    def fetch_run(self, run_id: str) -> ClassificationRunRecord | None:
        return self.fetch_one("SELECT * FROM classification_runs WHERE id = ?", (run_id,))

    def map_row(self, row: sqlite3.Row) -> ClassificationRunRecord:
        data = row_to_dict(row)
        data["estimated_cost_usd"] = str(data["estimated_cost_usd"])
        return ClassificationRunRecord.model_validate(data)


def _format_datetime(value: datetime) -> str:
    return value.isoformat()
