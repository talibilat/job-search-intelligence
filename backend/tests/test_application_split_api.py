from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
APPLIED_AT = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
REJECTED_AT = datetime(2026, 7, 3, 17, 30, tzinfo=UTC)
FEEDBACK_AT = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)


def test_post_application_split_moves_events_and_records_audit(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
            extract_note="Role was filled.",
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
            "reason": "The rejection belongs to a separate application.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert new_application_id.startswith("manual-split-")
    assert payload["source_application"]["id"] == "app-merged"
    assert payload["source_application"]["current_status"] == "applied"
    assert payload["new_application"]["company"] == "Beta Labs"
    assert payload["new_application"]["role_title"] == "Data Engineer"
    assert payload["new_application"]["source"] == "linkedin"
    assert payload["new_application"]["current_status"] == "rejected"
    assert payload["new_application"]["tech_stack"] == []
    assert payload["moved_events"][0]["id"] == "event-rejected"
    assert payload["moved_events"][0]["application_id"] == new_application_id
    assert payload["correction"]["application_id"] == "app-merged"
    assert payload["correction"]["correction_type"] == "split"
    assert payload["correction"]["before_json"]["source_application"]["id"] == "app-merged"
    assert payload["correction"]["after_json"]["new_application"]["id"] == new_application_id
    assert payload["correction"]["after_json"]["moved_event_ids"] == ["event-rejected"]

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            "SELECT current_status, first_seen_at, last_activity_at FROM applications WHERE id = ?",
            ("app-merged",),
        ).fetchone()
        assert source == ("applied", APPLIED_AT.isoformat(), APPLIED_AT.isoformat())

        target = db.execute(
            "SELECT company, role_title, current_status FROM applications WHERE id = ?",
            (new_application_id,),
        ).fetchone()
        assert target == ("Beta Labs", "Data Engineer", "rejected")

        reassigned_event = db.execute(
            "SELECT application_id FROM application_events WHERE id = ?",
            ("event-rejected",),
        ).fetchone()
        assert reassigned_event == (new_application_id,)

        corrections = db.execute(
            "SELECT correction_type FROM application_corrections WHERE application_id = ?",
            ("app-merged",),
        ).fetchall()
        assert corrections == [("split",)]


def test_post_application_split_preserves_terminal_status_priority(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_raw_email(connection, "email-feedback")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=FEEDBACK_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-feedback",
            application_id="app-merged",
            email_id="email-feedback",
            event_type="feedback",
            event_at=FEEDBACK_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected", "event-feedback"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert payload["new_application"]["current_status"] == "rejected"

    with sqlite3.connect(database_path) as db:
        target = db.execute(
            "SELECT current_status FROM applications WHERE id = ?",
            (new_application_id,),
        ).fetchone()
        assert target == ("rejected",)


def test_post_application_split_preserves_locked_source_status(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="withdrawn",
            last_activity_at=REJECTED_AT,
            manual_lock=True,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_application"]["current_status"] == "withdrawn"
    assert payload["source_application"]["manual_lock"] is True

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            """
            SELECT current_status, first_seen_at, last_activity_at, manual_lock
            FROM applications
            WHERE id = ?
            """,
            ("app-merged",),
        ).fetchone()
        assert source == (
            "withdrawn",
            APPLIED_AT.isoformat(),
            APPLIED_AT.isoformat(),
            1,
        )


def test_post_application_split_preserves_target_segmentation_fields(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
                "salary_min": 120000,
                "salary_max": 150000,
                "currency": "USD",
                "location": "New York, NY",
                "work_mode": "hybrid",
                "seniority": "senior",
                "sponsorship": "offered",
                "tech_stack": ["Python", "FastAPI"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert payload["new_application"]["salary_min"] == 120000
    assert payload["new_application"]["salary_max"] == 150000
    assert payload["new_application"]["currency"] == "USD"
    assert payload["new_application"]["location"] == "New York, NY"
    assert payload["new_application"]["work_mode"] == "hybrid"
    assert payload["new_application"]["seniority"] == "senior"
    assert payload["new_application"]["sponsorship"] == "offered"
    assert payload["new_application"]["tech_stack"] == ["Python", "FastAPI"]

    with sqlite3.connect(database_path) as db:
        target = db.execute(
            """
            SELECT salary_min, salary_max, currency, location, work_mode,
                   seniority, sponsorship, tech_stack
            FROM applications
            WHERE id = ?
            """,
            (new_application_id,),
        ).fetchone()
        assert target == (
            120000,
            150000,
            "USD",
            "New York, NY",
            "hybrid",
            "senior",
            "offered",
            '["Python","FastAPI"]',
        )


def migrated_connection(database_path: Path) -> sqlite3.Connection:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    connection = sqlite3.connect(str(database_path))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


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
            "Application update",
            NOW.isoformat(),
            "Synthetic job-search email body.",
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
    company: str,
    role_title: str,
    first_seen_at: datetime,
    current_status: str,
    last_activity_at: datetime,
    manual_lock: bool = False,
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at,
            current_status, salary_min, salary_max, currency,
            location, work_mode, seniority, sponsorship, tech_stack,
            last_activity_at, manual_lock, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            company,
            role_title,
            "other",
            first_seen_at.isoformat(),
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            "[]",
            last_activity_at.isoformat(),
            int(manual_lock),
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    email_id: str,
    event_type: str,
    event_at: datetime,
    extract_note: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at, extract_note
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            application_id,
            email_id,
            event_type,
            event_at.isoformat(),
            extract_note,
        ),
    )
