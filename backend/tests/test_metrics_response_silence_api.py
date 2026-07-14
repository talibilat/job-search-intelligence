from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository
from app.db.repositories.event import EventRepository
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_get_response_silence_metric_counts_human_response_events(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_application_with_events(
            connection,
            application_id="application-response",
            event_types=("applied", "response", "rejection"),
        )
        insert_application_with_events(
            connection,
            application_id="application-interview",
            event_types=("applied", "interview_scheduled"),
        )
        insert_application_with_events(
            connection,
            application_id="application-silent",
            event_types=("applied",),
        )
        insert_application_with_events(
            connection,
            application_id="application-ghosted",
            event_types=("applied", "ghost_inferred"),
        )

    client = create_test_client(database_path)

    response = client.get("/metrics/response-silence")

    assert response.status_code == 200
    assert response.json() == {
        "question_id": "Q-04",
        "total_applications": 4,
        "human_response_count": 2,
        "silent_count": 2,
    }


def test_response_silence_metric_returns_zero_counts_for_empty_database(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/metrics/response-silence")

    assert response.status_code == 200
    assert response.json() == {
        "question_id": "Q-04",
        "total_applications": 0,
        "human_response_count": 0,
        "silent_count": 0,
    }


def test_response_silence_metric_composes_every_dashboard_filter(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_application_with_events(
            connection,
            application_id="matching-application",
            event_types=("applied", "response"),
            company="Filter Labs",
            role_title="Platform Engineer",
            source="referral",
            current_status="in_review",
            first_seen_at="2026-07-10T09:00:00+00:00",
            salary_min=140000,
            salary_max=170000,
            sponsorship="offered",
            work_mode="remote",
        )
        insert_application_with_events(
            connection,
            application_id="nonmatching-application",
            event_types=("applied",),
        )

    response = create_test_client(database_path).get(
        "/metrics/response-silence",
        params={
            "status": "in_review",
            "source": "referral",
            "sponsorship": "offered",
            "first_seen_from": "2026-07-01T00:00:00Z",
            "first_seen_to": "2026-07-31T23:59:59Z",
            "role": "platform",
            "salary_min": 130000,
            "salary_max": 180000,
            "work_mode": "remote",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "question_id": "Q-04",
        "total_applications": 1,
        "human_response_count": 1,
        "silent_count": 0,
    }


def test_response_silence_metric_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/response-silence"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/ResponseSilenceMetric"


def create_test_client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        sync_on_open=False,
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


def insert_application_with_events(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    event_types: tuple[str, ...],
    company: str = "Acme Corp",
    role_title: str = "Software Engineer",
    source: str = "linkedin",
    current_status: str = "applied",
    first_seen_at: str = "2026-07-01T09:00:00+00:00",
    salary_min: int | None = None,
    salary_max: int | None = None,
    sponsorship: str = "unknown",
    work_mode: str | None = None,
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=company,
        role_title=role_title,
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
        last_activity_at="2026-07-03T10:00:00+00:00",
        created_at="2026-07-01T09:01:00+00:00",
        updated_at="2026-07-03T10:01:00+00:00",
        salary_min=salary_min,
        salary_max=salary_max,
        sponsorship=sponsorship,
        work_mode=work_mode,
    )
    event_repository = EventRepository(connection)
    for index, event_type in enumerate(event_types, start=1):
        email_id = None if event_type == "ghost_inferred" else f"{application_id}-email-{index}"
        if email_id is not None:
            insert_raw_email(connection, email_id=email_id)
        event_repository.upsert_event(
            id=f"{application_id}-event-{index}",
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=f"2026-07-0{index}T09:00:00+00:00",
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
            f"thread-{email_id}",
            "jobs@example.test",
            "applicant@example.test",
            "Application update",
            "2026-07-01T09:00:00+00:00",
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            "2026-07-01T09:01:00+00:00",
        ),
    )
