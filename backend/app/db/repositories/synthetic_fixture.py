from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.db.repositories.base import BaseRepository
from app.models.synthetic_fixture import SyntheticFixtureFile, SyntheticFixtureLoadResult


class SyntheticFixtureRepository(BaseRepository[sqlite3.Row]):
    """Load private-data-free synthetic fixtures into local SQLite."""

    def load_file(self, fixture_path: Path) -> SyntheticFixtureLoadResult:
        fixture = SyntheticFixtureFile.model_validate(json.loads(fixture_path.read_text()))
        return self.load_fixture(fixture)

    def load_fixture(self, fixture: SyntheticFixtureFile) -> SyntheticFixtureLoadResult:
        should_commit = not self.connection.in_transaction
        self.execute("PRAGMA foreign_keys = ON")

        with self.transaction():
            self._create_tables()
            self._load_emails(fixture)
            self._load_classifications(fixture)
            self._load_applications(fixture)
            self._load_events(fixture)

        if should_commit:
            self.connection.commit()

        return SyntheticFixtureLoadResult(
            fixture_id=fixture.fixture_id,
            email_count=len(fixture.emails),
            classification_count=len(fixture.classifications),
            application_count=len(fixture.applications),
            event_count=len(fixture.events),
        )

    def map_row(self, row: sqlite3.Row) -> sqlite3.Row:
        return row

    def _create_tables(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_emails (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                from_addr TEXT,
                to_addr TEXT,
                subject TEXT,
                sent_at TEXT,
                body_text TEXT,
                body_retention_state TEXT NOT NULL,
                labels TEXT NOT NULL,
                provider TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """,
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS email_classifications (
                email_id TEXT PRIMARY KEY,
                is_job_related INTEGER NOT NULL,
                category TEXT NOT NULL,
                confidence REAL NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                classified_at TEXT NOT NULL,
                FOREIGN KEY (email_id) REFERENCES raw_emails (id) ON DELETE CASCADE
            )
            """,
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                role_title TEXT NOT NULL,
                source TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                current_status TEXT NOT NULL,
                salary_min INTEGER,
                salary_max INTEGER,
                currency TEXT,
                location TEXT,
                work_mode TEXT,
                seniority TEXT,
                sponsorship TEXT NOT NULL,
                tech_stack TEXT NOT NULL,
                last_activity_at TEXT NOT NULL,
                manual_lock INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS application_events (
                id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL,
                email_id TEXT,
                event_type TEXT NOT NULL,
                event_at TEXT NOT NULL,
                extract_note TEXT,
                CHECK (
                    (event_type = 'ghost_inferred' AND email_id IS NULL)
                    OR (event_type != 'ghost_inferred' AND email_id IS NOT NULL)
                ),
                FOREIGN KEY (application_id) REFERENCES applications (id) ON DELETE CASCADE,
                FOREIGN KEY (email_id) REFERENCES raw_emails (id) ON DELETE CASCADE
            )
            """,
        )

    def _load_emails(self, fixture: SyntheticFixtureFile) -> None:
        self.execute_many(
            """
            INSERT OR REPLACE INTO raw_emails (
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
            """,
            [
                (
                    email.id,
                    email.thread_id,
                    email.from_addr,
                    email.to_addr,
                    email.subject,
                    _format_datetime(email.sent_at),
                    email.body_text,
                    email.body_retention_state.value,
                    _format_json_array(email.labels),
                    email.provider.value,
                    _format_datetime(email.ingested_at),
                )
                for email in fixture.emails
            ],
        )

    def _load_classifications(self, fixture: SyntheticFixtureFile) -> None:
        self.execute_many(
            """
            INSERT OR REPLACE INTO email_classifications (
                email_id,
                is_job_related,
                category,
                confidence,
                model,
                prompt_version,
                classified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    classification.email_id,
                    int(classification.is_job_related),
                    classification.category.value,
                    classification.confidence,
                    classification.model,
                    classification.prompt_version,
                    _format_datetime(classification.classified_at),
                )
                for classification in fixture.classifications
            ],
        )

    def _load_applications(self, fixture: SyntheticFixtureFile) -> None:
        self.execute_many(
            """
            INSERT OR REPLACE INTO applications (
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
                tech_stack,
                last_activity_at,
                manual_lock,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    application.id,
                    application.company,
                    application.role_title,
                    application.source.value,
                    _format_datetime(application.first_seen_at),
                    application.current_status.value,
                    application.salary_min,
                    application.salary_max,
                    application.currency,
                    application.location,
                    application.work_mode.value if application.work_mode is not None else None,
                    application.seniority,
                    application.sponsorship.value,
                    _format_json_array(application.tech_stack),
                    _format_datetime(application.last_activity_at),
                    int(application.manual_lock),
                    _format_datetime(application.created_at),
                    _format_datetime(application.updated_at),
                )
                for application in fixture.applications
            ],
        )

    def _load_events(self, fixture: SyntheticFixtureFile) -> None:
        self.execute_many(
            """
            INSERT OR REPLACE INTO application_events (
                id,
                application_id,
                email_id,
                event_type,
                event_at,
                extract_note
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event.id,
                    event.application_id,
                    event.email_id,
                    event.event_type.value,
                    _format_datetime(event.event_at),
                    event.extract_note,
                )
                for event in fixture.events
            ],
        )


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _format_json_array(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), separators=(",", ":"))
