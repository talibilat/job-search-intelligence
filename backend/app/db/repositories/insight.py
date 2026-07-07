from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import (
    ApplicationEventType,
    ApplicationStatus,
    InsightInputEvidence,
    InsightRecord,
    InsightType,
)


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

    def count_applications(self) -> int:
        row = self.execute("SELECT COUNT(*) AS count FROM applications").fetchone()
        if row is None:
            return 0
        return int(row["count"])

    def count_applications_by_status(self) -> dict[str, int]:
        rows = self.execute(
            """
            SELECT current_status AS value, COUNT(*) AS count
            FROM applications
            WHERE current_status IS NOT NULL
            GROUP BY current_status
            ORDER BY current_status
            """,
        ).fetchall()
        return _count_rows_to_dict(rows)

    def count_applications_by_source(self) -> dict[str, int]:
        rows = self.execute(
            """
            SELECT source AS value, COUNT(*) AS count
            FROM applications
            WHERE source IS NOT NULL
            GROUP BY source
            ORDER BY source
            """,
        ).fetchall()
        return _count_rows_to_dict(rows)

    def count_applications_by_sponsorship(self) -> dict[str, int]:
        rows = self.execute(
            """
            SELECT sponsorship AS value, COUNT(*) AS count
            FROM applications
            WHERE sponsorship IS NOT NULL
            GROUP BY sponsorship
            ORDER BY sponsorship
            """,
        ).fetchall()
        return _count_rows_to_dict(rows)

    def count_applications_by_work_mode(self) -> dict[str, int]:
        rows = self.execute(
            """
            SELECT work_mode AS value, COUNT(*) AS count
            FROM applications
            WHERE work_mode IS NOT NULL
            GROUP BY work_mode
            ORDER BY work_mode
            """,
        ).fetchall()
        return _count_rows_to_dict(rows)

    def count_events_by_type(self) -> dict[str, int]:
        rows = self.execute(
            """
            SELECT event_type AS value, COUNT(*) AS count
            FROM application_events
            WHERE event_type IS NOT NULL
            GROUP BY event_type
            ORDER BY event_type
            """,
        ).fetchall()
        return _count_rows_to_dict(rows)

    def count_rejected_application_skills(self) -> dict[str, int]:
        rows = self.execute(
            """
            SELECT id, tech_stack
            FROM applications
            WHERE current_status = 'rejected'
            ORDER BY id
            """,
        ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            skills = {
                skill.strip()
                for skill in json.loads(str(row["tech_stack"]))
                if isinstance(skill, str) and skill.strip()
            }
            for skill in skills:
                counts[skill] = counts.get(skill, 0) + 1
        return dict(sorted(counts.items()))

    def list_input_evidence(
        self,
        *,
        application_statuses: tuple[ApplicationStatus, ...] = (),
        event_types: tuple[ApplicationEventType, ...] = (),
        newest_first: bool = False,
    ) -> list[InsightInputEvidence]:
        """Return cited application and email evidence matching service-owned scope."""

        where_clauses: list[str] = []
        parameters: list[object] = []
        if application_statuses:
            where_clauses.append(
                f"applications.current_status IN ({_placeholders(len(application_statuses))})",
            )
            parameters.extend(application_statuses)
        if event_types:
            where_clauses.append(
                f"application_events.event_type IN ({_placeholders(len(event_types))})",
            )
            parameters.extend(event_types)

        sql = """
            SELECT
                applications.id AS application_id,
                applications.company AS company,
                applications.role_title AS role_title,
                applications.current_status AS application_status,
                applications.source AS source,
                applications.sponsorship AS sponsorship,
                applications.work_mode AS work_mode,
                applications.tech_stack AS tech_stack,
                application_events.id AS event_id,
                application_events.email_id AS email_id,
                application_events.event_type AS event_type,
                application_events.event_at AS event_at,
                application_events.extract_note AS extract_note,
                raw_emails.subject AS email_subject,
                raw_emails.from_addr AS email_from,
                raw_emails.sent_at AS email_sent_at,
                CASE
                    WHEN raw_emails.body_retention_state = 'retained'
                    THEN raw_emails.body_text
                    ELSE NULL
                END AS email_body_text
            FROM applications
            LEFT JOIN application_events
                ON application_events.application_id = applications.id
            LEFT JOIN raw_emails
                ON raw_emails.id = application_events.email_id
        """
        if where_clauses:
            sql = f"{sql} WHERE {' OR '.join(where_clauses)}"
        direction = "DESC" if newest_first else "ASC"
        sql = f"""
            {sql}
            ORDER BY
                COALESCE(application_events.event_at, applications.first_seen_at) {direction},
                applications.id,
                application_events.id
        """
        rows = self.execute(sql, tuple(parameters)).fetchall()
        return [_map_input_evidence(row) for row in rows]

    def map_row(self, row: sqlite3.Row) -> InsightRecord:
        return InsightRecord.model_validate(row_to_dict(row))


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _map_input_evidence(row: sqlite3.Row) -> InsightInputEvidence:
    data = row_to_dict(row)
    data["citation_id"] = _build_citation_id(
        application_id=str(data["application_id"]),
        event_id=_optional_str(data["event_id"]),
        email_id=_optional_str(data["email_id"]),
    )
    return InsightInputEvidence.model_validate(data)


def _build_citation_id(
    *,
    application_id: str,
    event_id: str | None,
    email_id: str | None,
) -> str:
    parts = [f"application:{application_id}"]
    if event_id is not None:
        parts.append(f"event:{event_id}")
    if email_id is not None:
        parts.append(f"email:{email_id}")
    return "|".join(parts)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _count_rows_to_dict(rows: list[sqlite3.Row]) -> dict[str, int]:
    return {str(row["value"]): int(row["count"]) for row in rows}


def _placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))
