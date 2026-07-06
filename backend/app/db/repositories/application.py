from __future__ import annotations

import json
import sqlite3
from typing import Literal

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import (
    ApplicationRecord,
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)

type ApplicationUpsertOutcome = Literal[
    "upserted",
    "locked_unchanged",
    "manual_conflict",
    "merged_source",
]


class ApplicationRepository(BaseRepository[ApplicationRecord]):
    """Repository seam for canonical job applications."""

    def get_by_id(self, application_id: str) -> ApplicationRecord | None:
        return self.fetch_one("SELECT * FROM applications WHERE id = ?", (application_id,))

    def get_application(self, application_id: str) -> ApplicationRecord | None:
        return self.get_by_id(application_id)

    def list_applications(
        self,
        *,
        current_status: ApplicationStatus | None = None,
        source: ApplicationSource | None = None,
        sponsorship: SponsorshipStatus | None = None,
        first_seen_from: str | None = None,
        first_seen_to: str | None = None,
        role: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        work_mode: WorkMode | None = None,
    ) -> list[ApplicationRecord]:
        clauses: list[str] = []
        parameters: list[object] = []

        if current_status is not None:
            clauses.append("current_status = ?")
            parameters.append(current_status)
        if source is not None:
            clauses.append("source = ?")
            parameters.append(source)
        if sponsorship is not None:
            clauses.append("sponsorship = ?")
            parameters.append(sponsorship)
        if first_seen_from is not None:
            clauses.append("first_seen_at >= ?")
            parameters.append(first_seen_from)
        if first_seen_to is not None:
            clauses.append("first_seen_at <= ?")
            parameters.append(first_seen_to)
        if role is not None:
            stripped_role = role.strip().lower()
            if stripped_role:
                clauses.append("LOWER(role_title) LIKE ? ESCAPE '\\'")
                parameters.append(f"%{_escape_like(stripped_role)}%")
        if salary_min is not None:
            clauses.append("COALESCE(salary_max, salary_min) >= ?")
            parameters.append(salary_min)
        if salary_max is not None:
            clauses.append("COALESCE(salary_min, salary_max) <= ?")
            parameters.append(salary_max)
        if work_mode is not None:
            clauses.append("work_mode = ?")
            parameters.append(work_mode)

        sql = "SELECT * FROM applications"
        if clauses:
            sql = f"{sql} WHERE {' AND '.join(clauses)}"
        sql = f"{sql} ORDER BY first_seen_at DESC, id ASC"
        return self.fetch_all(sql, tuple(parameters))

    def list_ghost_inference_candidates(self, *, cutoff_at: str) -> list[ApplicationRecord]:
        """Return applied applications whose timeline has no response evidence."""

        return self.fetch_all(
            """
            SELECT applications.*
            FROM applications
            WHERE applications.current_status = 'applied'
              AND applications.last_activity_at <= ?
              AND EXISTS (
                SELECT 1
                FROM application_events
                WHERE application_events.application_id = applications.id
                  AND application_events.event_type = 'applied'
              )
              AND NOT EXISTS (
                SELECT 1
                FROM application_events
                WHERE application_events.application_id = applications.id
                  AND application_events.event_type IN (
                    'response',
                    'assessment',
                    'interview_scheduled',
                    'feedback',
                    'rejection',
                    'offer',
                    'ghost_inferred'
                  )
              )
            ORDER BY applications.last_activity_at ASC, applications.id ASC
            """,
            (cutoff_at,),
        )

    def update_timeline_status(
        self,
        *,
        application_id: str,
        current_status: str,
        last_activity_at: str,
        updated_at: str,
    ) -> bool:
        """Update only timeline-derived status fields for an unlocked application."""

        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                """
                UPDATE applications
                SET current_status = ?,
                    last_activity_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND manual_lock = 0
                """,
                (current_status, last_activity_at, updated_at, application_id),
            )
        if should_commit:
            self.connection.commit()
        return cursor.rowcount > 0

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
    ) -> ApplicationUpsertOutcome:
        """Insert or update one application row idempotently.

        The deterministic ``id`` (derived from the grouping key) acts as
        the conflict target: re-running the same grouping key updates the
        row rather than creating a duplicate.
        """

        if self._is_deleted_merge_source(id):
            return "merged_source"

        existing = self.get_application(id)
        if existing is not None and existing.manual_lock:
            if _locked_application_matches(
                existing=existing,
                company=company,
                role_title=role_title,
                source=source,
                current_status=current_status,
                salary_min=salary_min,
                salary_max=salary_max,
                currency=currency,
                location=location,
                work_mode=work_mode,
                seniority=seniority,
                sponsorship=sponsorship,
                tech_stack=tech_stack or [],
            ):
                return "locked_unchanged"
            return "manual_conflict"

        tech_stack_json = json.dumps(tech_stack or [], separators=(",", ":"))
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
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
                WHERE applications.manual_lock = 0
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
        return "upserted" if cursor.rowcount > 0 else "manual_conflict"

    def update_application_summary(
        self,
        *,
        id: str,
        company: str,
        role_title: str,
        source: str,
        first_seen_at: str,
        current_status: str,
        last_activity_at: str,
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
        tech_stack_json = json.dumps(tech_stack or [], separators=(",", ":"))
        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                """
                UPDATE applications
                SET company = ?,
                    role_title = ?,
                    source = ?,
                    first_seen_at = ?,
                    current_status = ?,
                    salary_min = ?,
                    salary_max = ?,
                    currency = ?,
                    location = ?,
                    work_mode = ?,
                    seniority = ?,
                    sponsorship = ?,
                    tech_stack = ?,
                    last_activity_at = ?,
                    manual_lock = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
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
                    updated_at,
                    id,
                ),
            )
        if should_commit:
            self.connection.commit()

    def delete_application(self, application_id: str) -> None:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                "DELETE FROM applications WHERE id = ?",
                (application_id,),
            )
        if should_commit:
            self.connection.commit()

    def _is_deleted_merge_source(self, application_id: str) -> bool:
        row = self.execute(
            """
            SELECT 1
            FROM application_corrections
            WHERE correction_type = 'merge'
              AND json_extract(after_json, '$.deleted_source_application_id') = ?
            LIMIT 1
            """,
            (application_id,),
        ).fetchone()
        return row is not None

    def update_timeline_summary(
        self,
        *,
        application_id: str,
        first_seen_at: str,
        current_status: str,
        company: str,
        role_title: str,
        source: str,
        salary_min: int | None,
        salary_max: int | None,
        currency: str | None,
        location: str | None,
        work_mode: str | None,
        seniority: str | None,
        sponsorship: str,
        tech_stack: list[str],
        last_activity_at: str,
        updated_at: str,
        manual_lock: bool = False,
    ) -> bool:
        """Update timeline-derived summary fields for an existing application."""

        tech_stack_json = json.dumps(tech_stack, separators=(",", ":"))
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                """
                UPDATE applications
                SET first_seen_at = ?,
                    current_status = ?,
                    company = ?,
                    role_title = ?,
                    source = ?,
                    salary_min = ?,
                    salary_max = ?,
                    currency = ?,
                    location = ?,
                    work_mode = ?,
                    seniority = ?,
                    sponsorship = ?,
                    tech_stack = ?,
                    last_activity_at = ?,
                    manual_lock = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    first_seen_at,
                    current_status,
                    company,
                    role_title,
                    source,
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
                    updated_at,
                    application_id,
                ),
            )
        if should_commit:
            self.connection.commit()
        return cursor.rowcount > 0

    def map_row(self, row: sqlite3.Row) -> ApplicationRecord:
        return ApplicationRecord.model_validate(row_to_dict(row))


def _locked_application_matches(
    *,
    existing: ApplicationRecord,
    company: str,
    role_title: str,
    source: str,
    current_status: str,
    salary_min: int | None,
    salary_max: int | None,
    currency: str | None,
    location: str | None,
    work_mode: str | None,
    seniority: str | None,
    sponsorship: str,
    tech_stack: list[str],
) -> bool:
    return (
        existing.company == company
        and existing.role_title == role_title
        and existing.source == source
        and existing.current_status == current_status
        and existing.salary_min == salary_min
        and existing.salary_max == salary_max
        and existing.currency == currency
        and existing.location == location
        and existing.work_mode == work_mode
        and existing.seniority == seniority
        and existing.sponsorship == sponsorship
        and existing.tech_stack == tech_stack
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
