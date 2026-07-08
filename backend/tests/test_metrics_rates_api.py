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


def test_metrics_rates_returns_overall_response_rate_with_counts(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application_with_events(connection, "app-response", ("applied", "response"))
        insert_application_with_events(
            connection,
            "app-rejection",
            ("applied", "rejection"),
            current_status="rejected",
        )
        insert_application_with_events(
            connection,
            "app-multiple-responses",
            ("applied", "response", "interview_scheduled"),
        )
        insert_application_with_events(
            connection,
            "app-silent",
            ("applied",),
            event_date_prefix="2020-01",
        )
        insert_application_with_events(
            connection,
            "app-ghosted",
            ("applied", "ghost_inferred"),
            current_status="ghosted",
            event_date_prefix="2020-02",
        )

    response = create_test_client(database_path).get("/metrics/rates")

    assert response.status_code == 200
    assert response.json() == {
        "overall_response_rate": {
            "numerator": 3,
            "denominator": 5,
            "rate": 0.6,
        },
        "rejection_rate": {
            "numerator": 1,
            "denominator": 5,
            "rate": 0.2,
        },
        "ghost_rate": {
            "numerator": 2,
            "denominator": 5,
            "rate": 0.4,
        },
        "application_to_interview_rate": {
            "numerator": 1,
            "denominator": 5,
            "rate": 0.2,
        },
    }


def test_metrics_rates_returns_null_rate_when_no_applications(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)

    response = create_test_client(database_path).get("/metrics/rates")

    assert response.status_code == 200
    assert response.json() == {
        "overall_response_rate": {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
        },
        "rejection_rate": {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
        },
        "ghost_rate": {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
        },
        "application_to_interview_rate": {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
        },
    }


def test_metrics_rates_endpoint_is_documented_in_openapi() -> None:
    response = TestClient(create_app()).get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/rates"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsRatesResponse"


def create_test_client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        ghost_threshold_days=30,
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
    application_id: str,
    event_types: tuple[str, ...],
    *,
    current_status: str = "applied",
    event_date_prefix: str = "2026-07",
) -> None:
    repository = ApplicationRepository(connection)
    repository.upsert_application(
        id=application_id,
        company=f"{application_id} Corp",
        role_title="Software Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status=current_status,
        last_activity_at="2026-07-01T09:00:00+00:00",
        created_at="2026-07-01T09:01:00+00:00",
        updated_at="2026-07-01T09:01:00+00:00",
        sponsorship="unknown",
        tech_stack=[],
    )
    for index, event_type in enumerate(event_types):
        email_id = None if event_type == "ghost_inferred" else f"{application_id}-email-{index}"
        if email_id is not None:
            insert_raw_email(connection, email_id=email_id)
        EventRepository(connection).upsert_event(
            id=f"{application_id}-event-{index}",
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=f"{event_date_prefix}-{index + 1:02d}T09:00:00+00:00",
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
