from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)


def test_post_application_merge_merges_source_into_target(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "target-email")
        insert_raw_email(connection, "source-email")
        insert_application(connection, application_id="app-target")
        insert_application(
            connection,
            application_id="app-source",
            current_status="rejected",
            last_activity_at="2026-07-05T10:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-source-rejection",
            application_id="app-source",
            email_id="source-email",
            event_type="rejection",
            event_at="2026-07-05T10:00:00+00:00",
        )

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-target/merge",
        json={
            "source_application_id": "app-source",
            "reason": "Duplicate application.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target_application_id"] == "app-target"
    assert body["source_application_id"] == "app-source"
    assert body["moved_event_count"] == 1
    assert body["application"]["id"] == "app-target"
    assert body["application"]["current_status"] == "rejected"
    assert body["application"]["manual_lock"] is True
    assert body["correction"]["application_id"] == "app-target"
    assert body["correction"]["correction_type"] == "merge"


def test_post_application_merge_returns_typed_not_found_error(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-target")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-target/merge",
        json={"source_application_id": "missing-source"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Source application was not found.",
            "details": [],
        }
    }


def test_post_application_merge_rejects_blank_source_after_trimming(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-target")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-target/merge",
        json={"source_application_id": "   "},
    )

    assert response.status_code == 422


def test_post_application_merge_rejects_unexpected_payload_fields(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-target")
        insert_application(connection, application_id="app-source")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-target/merge",
        json={
            "source_application_id": "app-source",
            "delete_target": True,
        },
    )

    assert response.status_code == 422


def test_application_merge_openapi_documents_typed_errors() -> None:
    app = create_app()

    responses = app.openapi()["paths"]["/applications/{application_id}/merge"]["post"]["responses"]

    assert responses["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }


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
    current_status: str = "applied",
    last_activity_at: str = "2026-07-01T09:00:00+00:00",
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
            "2026-07-01T09:00:00+00:00",
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            json.dumps([]),
            last_activity_at,
            0,
            "2026-07-01T09:00:00+00:00",
            "2026-07-01T09:00:00+00:00",
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
