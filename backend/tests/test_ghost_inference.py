from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_post_ghost_inference_marks_silent_applications_idempotently(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_application(
            connection,
            application_id="app-silent",
            current_status="applied",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-05-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-silent",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=45)

    first_response = client.post("/applications/ghost-inference")
    second_response = client.post("/applications/ghost-inference")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_body = first_response.json()
    second_body = second_response.json()
    assert first_body["threshold_days"] == 45
    assert first_body["applications_ghosted"] == 1
    assert first_body["ghosted_application_ids"] == ["app-silent"]
    assert first_body["manual_conflict_count"] == 0
    assert first_body["manual_conflict_application_ids"] == []
    assert second_body["applications_ghosted"] == 0
    assert second_body["ghosted_application_ids"] == []

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-silent",),
        ).fetchall()
        application_count = connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        ghost_events = connection.execute(
            """
            SELECT email_id, event_type, event_at
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-silent",),
        ).fetchall()

    assert application_rows == [("ghosted", "2026-06-15T09:00:00+00:00")]
    assert application_count == 1
    assert ghost_events == [(None, "ghost_inferred", "2026-06-15T09:00:00+00:00")]


def test_post_ghost_inference_surfaces_manual_lock_conflict(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_application(
            connection,
            application_id="app-locked",
            current_status="applied",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-05-01T09:00:00+00:00",
            manual_lock=True,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-locked",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["applications_ghosted"] == 0
    assert body["ghosted_application_ids"] == []
    assert body["manual_conflict_count"] == 1
    assert body["manual_conflict_application_ids"] == ["app-locked"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, manual_lock FROM applications WHERE id = ?",
            ("app-locked",),
        ).fetchall()
        ghost_event_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-locked",),
        ).fetchone()[0]

    assert application_rows == [("applied", 1)]
    assert ghost_event_count == 0


def create_test_client(database_path: Path, *, ghost_threshold_days: int) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        sync_on_open=False,
        ghost_threshold_days=ghost_threshold_days,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    current_status: str,
    first_seen_at: str,
    last_activity_at: str,
    manual_lock: bool = False,
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at, current_status,
            salary_min, salary_max, currency, location, work_mode, seniority,
            sponsorship, tech_stack, last_activity_at, manual_lock,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            "Acme Corp",
            "Software Engineer",
            "company_site",
            first_seen_at,
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            "[]",
            last_activity_at,
            int(manual_lock),
            first_seen_at,
            first_seen_at,
        ),
    )
    connection.commit()


def insert_raw_email(connection: sqlite3.Connection, *, email_id: str) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            "thread-ghost",
            "jobs@example.test",
            "applicant@example.test",
            "Application received",
            "2026-05-01T09:00:00+00:00",
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            "2026-05-01T09:01:00+00:00",
        ),
    )
    connection.commit()


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    email_id: str | None,
    event_type: str,
    event_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at, extract_note,
            extracted_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, application_id, email_id, event_type, event_at, None, None),
    )
    connection.commit()
