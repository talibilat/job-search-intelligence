from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository, EventRepository
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_metrics_summary_counts_interview_invitations_from_event_history(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="application-with-two-interviews")
        insert_application(
            connection,
            application_id="application-with-one-interview",
            current_status="offer",
        )
        insert_application(
            connection,
            application_id="application-status-only-interview",
            current_status="interview",
        )
        insert_event(
            connection,
            event_id="event-interview-1",
            application_id="application-with-two-interviews",
            email_id="email-interview-1",
            event_type="interview_scheduled",
        )
        insert_event(
            connection,
            event_id="event-interview-2",
            application_id="application-with-two-interviews",
            email_id="email-interview-2",
            event_type="interview_scheduled",
        )
        insert_event(
            connection,
            event_id="event-rejection",
            application_id="application-with-two-interviews",
            email_id="email-rejection",
            event_type="rejection",
        )
        insert_event(
            connection,
            event_id="event-interview-3",
            application_id="application-with-one-interview",
            email_id="email-interview-3",
            event_type="interview_scheduled",
        )

    client = create_test_client(database_path)

    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["interview_invitation_count"] == 3
    assert body["ghosted_applications"] == 0
    assert "evaluated_at" in body


def test_metrics_summary_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/summary"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsSummaryResponse"


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def create_test_client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        sync_on_open=False,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    current_status: str = "rejected",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company="Acme Corp",
        role_title="Software Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status=current_status,
        last_activity_at="2026-07-03T10:00:00+00:00",
        created_at="2026-07-01T09:01:00+00:00",
        updated_at="2026-07-03T10:01:00+00:00",
        salary_min=None,
        salary_max=None,
        currency=None,
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=["Python", "FastAPI"],
    )
    connection.commit()


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    email_id: str,
    event_type: str,
) -> None:
    insert_raw_email(connection, email_id=email_id)
    EventRepository(connection).upsert_event(
        id=event_id,
        application_id=application_id,
        email_id=email_id,
        event_type=event_type,
        event_at="2026-07-03T10:00:00+00:00",
        extract_note="Synthetic timeline event.",
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
            "thread-42",
            "jobs@example.test",
            "applicant@example.test",
            "Application update",
            "2026-07-03T10:00:00+00:00",
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            "2026-07-03T10:01:00+00:00",
        ),
    )
    connection.commit()
