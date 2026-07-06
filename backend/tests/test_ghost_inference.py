from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from app.pipeline.aggregate import make_event_id
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


def test_post_ghost_inference_removes_stale_ghost_when_response_predates_threshold(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_raw_email(
            connection,
            email_id="email-response",
            sent_at="2026-05-15T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-stale",
            current_status="ghosted",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-05-31T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-stale",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-response",
            application_id="app-stale",
            email_id="email-response",
            event_type="response",
            event_at="2026-05-15T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-ghost",
            application_id="app-stale",
            email_id=None,
            event_type="ghost_inferred",
            event_at="2026-05-31T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["applications_ghosted"] == 0
    assert body["ghost_retraction_count"] == 1
    assert body["retracted_application_ids"] == ["app-stale"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-stale",),
        ).fetchall()
        ghost_event_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-stale",),
        ).fetchone()[0]

    assert application_rows == [("in_review", "2026-05-15T09:00:00+00:00")]
    assert ghost_event_count == 0


def test_post_ghost_inference_recomputes_existing_ghost_when_threshold_changes(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_application(
            connection,
            application_id="app-threshold",
            current_status="ghosted",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-05-31T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-threshold",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-ghost-old",
            application_id="app-threshold",
            email_id=None,
            event_type="ghost_inferred",
            event_at="2026-05-31T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=45)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["applications_ghosted"] == 1
    assert body["ghosted_application_ids"] == ["app-threshold"]
    assert body["ghost_retraction_count"] == 1
    assert body["retracted_application_ids"] == ["app-threshold"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-threshold",),
        ).fetchall()
        ghost_events = connection.execute(
            """
            SELECT event_at
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-threshold",),
        ).fetchall()

    assert application_rows == [("ghosted", "2026-06-15T09:00:00+00:00")]
    assert ghost_events == [("2026-06-15T09:00:00+00:00",)]


def test_post_ghost_inference_uses_response_order_after_latest_applied_event(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-response", sent_at="2026-05-15T09:00:00+00:00")
        insert_raw_email(connection, email_id="email-applied", sent_at="2026-06-01T09:00:00+00:00")
        insert_application(
            connection,
            application_id="app-later-applied",
            current_status="applied",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-06-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-response",
            application_id="app-later-applied",
            email_id="email-response",
            event_type="response",
            event_at="2026-05-15T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-later-applied",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-06-01T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["applications_ghosted"] == 1
    assert body["ghosted_application_ids"] == ["app-later-applied"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-later-applied",),
        ).fetchall()
        ghost_events = connection.execute(
            """
            SELECT event_at
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-later-applied",),
        ).fetchall()

    assert application_rows == [("ghosted", "2026-07-01T09:00:00+00:00")]
    assert ghost_events == [("2026-07-01T09:00:00+00:00",)]


def test_post_ghost_inference_reports_protected_ghost_event_conflict(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    ghosted_at = "2026-05-31T09:00:00+00:00"
    ghost_event_id = make_event_id(
        application_id="app-protected",
        email_id=None,
        event_type="ghost_inferred",
        event_at=ghosted_at,
    )
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_application(
            connection,
            application_id="app-protected",
            current_status="applied",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-05-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-protected",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )
        insert_event_edit_correction(
            connection,
            application_id="app-protected",
            event_id=ghost_event_id,
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["applications_ghosted"] == 0
    assert body["ghosted_application_ids"] == []
    assert body["manual_conflict_count"] == 1
    assert body["manual_conflict_application_ids"] == ["app-protected"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-protected",),
        ).fetchall()
        ghost_event_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-protected",),
        ).fetchone()[0]

    assert application_rows == [("applied", "2026-05-01T09:00:00+00:00")]
    assert ghost_event_count == 0


def test_post_ghost_inference_reconciles_stale_ghost_after_status_advances(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_raw_email(
            connection,
            email_id="email-response",
            sent_at="2026-06-10T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-advanced",
            current_status="in_review",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-06-10T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-advanced",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-ghost",
            application_id="app-advanced",
            email_id=None,
            event_type="ghost_inferred",
            event_at="2026-05-31T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-response",
            application_id="app-advanced",
            email_id="email-response",
            event_type="response",
            event_at="2026-06-10T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["ghost_retraction_count"] == 1
    assert body["retracted_application_ids"] == ["app-advanced"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-advanced",),
        ).fetchall()
        ghost_event_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-advanced",),
        ).fetchone()[0]

    assert application_rows == [("in_review", "2026-06-10T09:00:00+00:00")]
    assert ghost_event_count == 0


def test_post_ghost_inference_reports_protected_ghost_retraction_conflict(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-applied")
        insert_raw_email(
            connection,
            email_id="email-response",
            sent_at="2026-05-15T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-protected-retraction",
            current_status="ghosted",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-05-31T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-protected-retraction",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-05-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-response",
            application_id="app-protected-retraction",
            email_id="email-response",
            event_type="response",
            event_at="2026-05-15T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-ghost-protected",
            application_id="app-protected-retraction",
            email_id=None,
            event_type="ghost_inferred",
            event_at="2026-05-31T09:00:00+00:00",
        )
        insert_event_edit_correction(
            connection,
            application_id="app-protected-retraction",
            event_id="event-ghost-protected",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["ghost_retraction_count"] == 0
    assert body["retracted_application_ids"] == []
    assert body["manual_conflict_count"] == 1
    assert body["manual_conflict_application_ids"] == ["app-protected-retraction"]

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-protected-retraction",),
        ).fetchall()
        ghost_event_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-protected-retraction",),
        ).fetchone()[0]

    assert application_rows == [("ghosted", "2026-05-31T09:00:00+00:00")]
    assert ghost_event_count == 1


def test_post_ghost_inference_keeps_ghost_when_response_precedes_latest_applied(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-response", sent_at="2026-05-15T09:00:00+00:00")
        insert_raw_email(connection, email_id="email-applied", sent_at="2026-06-01T09:00:00+00:00")
        insert_application(
            connection,
            application_id="app-ordered-ghost",
            current_status="ghosted",
            first_seen_at="2026-05-01T09:00:00+00:00",
            last_activity_at="2026-07-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-response",
            application_id="app-ordered-ghost",
            email_id="email-response",
            event_type="response",
            event_at="2026-05-15T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-ordered-ghost",
            email_id="email-applied",
            event_type="applied",
            event_at="2026-06-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-ghost",
            application_id="app-ordered-ghost",
            email_id=None,
            event_type="ghost_inferred",
            event_at="2026-07-01T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.post("/applications/ghost-inference")

    assert response.status_code == 200
    body = response.json()
    assert body["ghost_retraction_count"] == 0
    assert body["retracted_application_ids"] == []

    with sqlite3.connect(database_path) as connection:
        application_rows = connection.execute(
            "SELECT current_status, last_activity_at FROM applications WHERE id = ?",
            ("app-ordered-ghost",),
        ).fetchall()
        ghost_event_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE application_id = ? AND event_type = 'ghost_inferred'
            """,
            ("app-ordered-ghost",),
        ).fetchone()[0]

    assert application_rows == [("ghosted", "2026-07-01T09:00:00+00:00")]
    assert ghost_event_count == 1


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


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    sent_at: str = "2026-05-01T09:00:00+00:00",
) -> None:
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
            sent_at,
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


def insert_event_edit_correction(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    event_id: str,
) -> None:
    event_snapshot = {"event": {"id": event_id}}
    connection.execute(
        """
        INSERT INTO application_corrections (
            application_id, correction_type, before_json, after_json, reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            "event_edit",
            json.dumps(event_snapshot),
            json.dumps(event_snapshot),
            "Protect manually edited ghost event identity.",
            "2026-05-02T09:00:00+00:00",
        ),
    )
    connection.commit()
