from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.pipeline.aggregate import make_event_id
from app.services.manual_edit import ManualApplicationEditService, ManualEditInvalidRequestError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)
APPLIED_AT = "2026-07-01T09:00:00+00:00"
INTERVIEW_AT = datetime(2026, 7, 7, 14, 0, tzinfo=UTC)


def test_manual_status_edit_locks_application_and_records_correction(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_application(connection, application_id="app-1", current_status="applied")
    connection.commit()

    service = make_service(connection)
    result = service.edit_status(
        application_id="app-1",
        current_status="rejected",
        reason="The rejection email was missed by extraction.",
    )

    assert result.application.id == "app-1"
    assert result.application.current_status == "rejected"
    assert result.application.manual_lock is True
    assert result.application.updated_at == NOW
    assert result.correction.application_id == "app-1"
    assert result.correction.correction_type == "status_edit"
    assert result.correction.reason == "The rejection email was missed by extraction."
    before_application = cast(dict[str, object], result.correction.before_json["application"])
    after_application = cast(dict[str, object], result.correction.after_json["application"])
    assert before_application["current_status"] == "applied"
    assert after_application["current_status"] == "rejected"

    outcome = ApplicationRepository(connection).upsert_application(
        id="app-1",
        company="Acme Corp",
        role_title="Software Engineer",
        source="other",
        first_seen_at=APPLIED_AT,
        current_status="offer",
        last_activity_at=APPLIED_AT,
        created_at=APPLIED_AT,
        updated_at=NOW.isoformat(),
    )
    assert outcome == "manual_conflict"


def test_manual_event_edit_updates_timeline_audits_and_blocks_reprocessing_overwrite(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1")
    insert_application(connection, application_id="app-1", current_status="applied")
    insert_event(
        connection,
        event_id="event-1",
        application_id="app-1",
        email_id="email-1",
        event_type="applied",
        event_at=APPLIED_AT,
        extract_note=None,
    )
    connection.commit()

    service = make_service(connection)
    result = service.edit_event(
        application_id="app-1",
        event_id="event-1",
        event_type="interview_scheduled",
        event_at=INTERVIEW_AT,
        email_id="email-1",
        extract_note="Recruiter scheduled a phone screen.",
        reason="The timeline should show the interview invite.",
    )

    expected_event_id = make_event_id(
        application_id="app-1",
        email_id="email-1",
        event_type="interview_scheduled",
        event_at=INTERVIEW_AT.isoformat(),
    )
    assert result.event.id == expected_event_id
    assert result.event.event_type == "interview_scheduled"
    assert result.event.event_at == INTERVIEW_AT
    assert result.event.extract_note == "Recruiter scheduled a phone screen."
    assert result.application.manual_lock is True
    assert result.application.last_activity_at == INTERVIEW_AT
    assert result.application.updated_at == NOW
    assert result.correction.application_id == "app-1"
    assert result.correction.correction_type == "event_edit"
    before_event = cast(dict[str, object], result.correction.before_json["event"])
    after_event = cast(dict[str, object], result.correction.after_json["event"])
    assert before_event["event_type"] == "applied"
    assert after_event["event_type"] == "interview_scheduled"

    outcome = EventRepository(connection).upsert_event(
        id="event-1",
        application_id="app-1",
        email_id="email-1",
        event_type="applied",
        event_at=APPLIED_AT,
        extract_note=None,
    )
    stored_event = EventRepository(connection).get_by_application_and_id(
        application_id="app-1",
        event_id=expected_event_id,
    )
    assert outcome == "manual_conflict"
    assert stored_event is not None
    assert stored_event.event_type == "interview_scheduled"
    assert stored_event.event_at == INTERVIEW_AT

    unchanged_outcome = EventRepository(connection).upsert_event(
        id=expected_event_id,
        application_id="app-1",
        email_id="email-1",
        event_type="interview_scheduled",
        event_at=INTERVIEW_AT.isoformat(),
        extract_note="Recruiter scheduled a phone screen.",
    )
    assert unchanged_outcome == "locked_unchanged"


def test_manual_event_edit_rejects_missing_source_email(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1")
    insert_application(connection, application_id="app-1", current_status="applied")
    insert_event(
        connection,
        event_id="event-1",
        application_id="app-1",
        email_id="email-1",
        event_type="applied",
        event_at=APPLIED_AT,
        extract_note=None,
    )
    connection.commit()

    service = make_service(connection)

    with pytest.raises(ManualEditInvalidRequestError):
        service.edit_event(
            application_id="app-1",
            event_id="event-1",
            email_id="missing-email",
            reason="Point this event at another source email.",
            update_email_id=True,
        )


def test_manual_event_edit_rejects_no_op(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1")
    insert_application(connection, application_id="app-1", current_status="applied")
    insert_event(
        connection,
        event_id="event-1",
        application_id="app-1",
        email_id="email-1",
        event_type="applied",
        event_at=APPLIED_AT,
        extract_note=None,
    )
    connection.commit()

    service = make_service(connection)

    with pytest.raises(ManualEditInvalidRequestError):
        service.edit_event(
            application_id="app-1",
            event_id="event-1",
            event_type="applied",
            reason="No event data changed.",
        )


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(str(database_path))


def make_service(connection: sqlite3.Connection) -> ManualApplicationEditService:
    return ManualApplicationEditService(
        application_repository=ApplicationRepository(connection),
        event_repository=EventRepository(connection),
        correction_repository=CorrectionRepository(connection),
        clock=lambda: NOW,
    )


def insert_raw_email(connection: sqlite3.Connection, email_id: str) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject,
            sent_at, body_text, body_retention_state, labels,
            provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "me@example.test",
            "Job update",
            NOW.isoformat(),
            "Test body content.",
            "retained",
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    current_status: str,
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at,
            current_status, salary_min, salary_max, currency,
            location, work_mode, seniority, sponsorship,
            tech_stack, last_activity_at, manual_lock,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            "Acme Corp",
            "Software Engineer",
            "other",
            APPLIED_AT,
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            json.dumps([]),
            APPLIED_AT,
            0,
            APPLIED_AT,
            APPLIED_AT,
        ),
    )


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    email_id: str,
    event_type: str,
    event_at: str,
    extract_note: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at, extract_note
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, application_id, email_id, event_type, event_at, extract_note),
    )
