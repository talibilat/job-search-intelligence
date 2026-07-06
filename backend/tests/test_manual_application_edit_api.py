from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from app.pipeline.aggregate import make_event_id
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)
APPLIED_AT = "2026-07-01T09:00:00+00:00"


def test_patch_application_status_edits_status_with_audit(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-1", current_status="applied")

    client = create_test_client(database_path)

    response = client.patch(
        "/applications/app-1/status",
        json={
            "current_status": "rejected",
            "reason": "The rejection email was missed by extraction.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["application"]["id"] == "app-1"
    assert body["application"]["current_status"] == "rejected"
    assert body["application"]["manual_lock"] is True
    assert body["correction"]["application_id"] == "app-1"
    assert body["correction"]["correction_type"] == "status_edit"


def test_patch_application_event_edits_timeline_event_with_audit(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "email-1")
        insert_application(connection, application_id="app-1", current_status="applied")
        insert_event(
            connection,
            event_id="event-1",
            application_id="app-1",
            email_id="email-1",
            event_type="applied",
            event_at=APPLIED_AT,
        )

    client = create_test_client(database_path)

    response = client.patch(
        "/applications/app-1/events/event-1",
        json={
            "event_type": "interview_scheduled",
            "event_at": "2026-07-07T14:00:00Z",
            "extract_note": "Recruiter scheduled a phone screen.",
            "reason": "The timeline should show the interview invite.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["id"] == make_event_id(
        application_id="app-1",
        email_id="email-1",
        event_type="interview_scheduled",
        event_at="2026-07-07T14:00:00+00:00",
    )
    assert body["event"]["event_type"] == "interview_scheduled"
    assert body["event"]["event_at"] == "2026-07-07T14:00:00Z"
    assert body["event"]["extract_note"] == "Recruiter scheduled a phone screen."
    assert body["application"]["manual_lock"] is True
    assert body["application"]["last_activity_at"] == "2026-07-07T14:00:00Z"
    assert body["correction"]["correction_type"] == "event_edit"


def test_patch_application_event_rejects_missing_source_email(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "email-1")
        insert_application(connection, application_id="app-1", current_status="applied")
        insert_event(
            connection,
            event_id="event-1",
            application_id="app-1",
            email_id="email-1",
            event_type="applied",
            event_at=APPLIED_AT,
        )

    client = create_test_client(database_path)

    response = client.patch(
        "/applications/app-1/events/event-1",
        json={"email_id": "missing-email"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Application event edit is invalid."


def test_patch_application_event_rejects_explicit_null_event_at(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "email-1")
        insert_application(connection, application_id="app-1", current_status="applied")
        insert_event(
            connection,
            event_id="event-1",
            application_id="app-1",
            email_id="email-1",
            event_type="applied",
            event_at=APPLIED_AT,
        )

    client = create_test_client(database_path)

    response = client.patch(
        "/applications/app-1/events/event-1",
        json={"event_at": None},
    )

    assert response.status_code == 422


def test_patch_application_event_returns_typed_not_found_error(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-1", current_status="applied")

    client = create_test_client(database_path)

    response = client.patch(
        "/applications/app-1/events/missing-event",
        json={"event_at": "2026-07-07T14:00:00Z"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Application event was not found.",
            "details": [],
        }
    }


def test_application_edit_openapi_documents_typed_errors() -> None:
    app = create_app()
    openapi = app.openapi()["paths"]

    status_responses = openapi["/applications/{application_id}/status"]["patch"]["responses"]
    event_responses = openapi["/applications/{application_id}/events/{event_id}"]["patch"][
        "responses"
    ]

    assert status_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert event_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert event_responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }


def create_test_client(database_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    return TestClient(app)


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


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
) -> None:
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at, extract_note
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, application_id, email_id, event_type, event_at, None),
    )
