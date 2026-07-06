from __future__ import annotations

import json
import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationRecord


class ApplicationRepository(BaseRepository[ApplicationRecord]):
    """Repository seam for canonical job applications."""

    def upsert_application(
        self,
        *,
        id: str,
        company: str,
        role_title: str,
        source: str,
        first_seen_at: str,
        current_status: str,
        last_activity_at: str,
        created_at: str,
        updated_at: str,
        salary_min: int | None = None,
        salary_max: int | None = None,
        currency: str | None = None,
        location: str | None = None,
        work_mode: str | None = None,
        seniority: str | None = None,
        sponsorship: str = "unknown",
        tech_stack: list[str] | None = None,
        manual_lock: bool = False,
    ) -> None:
        """Insert or update one application row idempotently.

        The deterministic ``id`` (derived from the grouping key) acts as
        the conflict target: re-running the same grouping key updates the
        row rather than creating a duplicate.
        """

        tech_stack_json = json.dumps(tech_stack or [], separators=(",", ":"))
        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                """
                INSERT INTO applications (
                    id, company, role_title, source,
                    first_seen_at, current_status,
                    salary_min, salary_max, currency,
                    location, work_mode, seniority, sponsorship,
                    tech_stack, last_activity_at, manual_lock,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    company = excluded.company,
                    role_title = excluded.role_title,
                    source = excluded.source,
                    current_status = excluded.current_status,
                    salary_min = excluded.salary_min,
                    salary_max = excluded.salary_max,
                    currency = excluded.currency,
                    location = excluded.location,
                    work_mode = excluded.work_mode,
                    seniority = excluded.seniority,
                    sponsorship = excluded.sponsorship,
                    tech_stack = excluded.tech_stack,
                    last_activity_at = excluded.last_activity_at,
                    updated_at = excluded.updated_at
                """,
                (
                    id,
                    company,
                    role_title,
                    source,
                    first_seen_at,
                    current_status,
                    salary_min,
                    salary_max,
                    currency,
                    location,
                    work_mode,
                    seniority,
                    sponsorship,
                    tech_stack_json,
                    last_activity_at,
                    int(manual_lock),
                    created_at,
                    updated_at,
                ),
            )
        if should_commit:
            self.connection.commit()

    def map_row(self, row: sqlite3.Row) -> ApplicationRecord:
        return ApplicationRecord.model_validate(row_to_dict(row))
