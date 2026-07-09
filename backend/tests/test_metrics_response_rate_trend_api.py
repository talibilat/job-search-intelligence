from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository, EventRepository, MetricsRepository
from app.main import create_app
from app.models.metrics import MetricsFilter
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_metrics_repository_returns_response_rate_trend(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-1",
            first_seen_at="2026-07-01T09:00:00+00:00",
            responded=True,
        )
        insert_application(
            connection,
            application_id="app-2",
            first_seen_at="2026-07-01T10:00:00+00:00",
            responded=False,
        )
        insert_application(
            connection,
            application_id="app-3",
            first_seen_at="2026-07-08T09:00:00+00:00",
            responded=True,
        )

        points = MetricsRepository(connection).get_response_rate_timeseries()

    assert [
        (point.period_start, point.response_count, point.application_count, point.response_rate)
        for point in points
    ] == [
        ("2026-07-01", 1, 2, 0.5),
        ("2026-07-08", 1, 1, 1.0),
    ]


def test_response_rate_trend_applies_filters(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="linkedin-response",
            first_seen_at="2026-07-01T09:00:00+00:00",
            responded=True,
            source="linkedin",
        )
        insert_application(
            connection,
            application_id="company-response",
            first_seen_at="2026-07-01T10:00:00+00:00",
            responded=True,
            source="company_site",
        )

        points = MetricsRepository(connection).get_response_rate_timeseries(
            filters=MetricsFilter(source="linkedin"),
        )

    assert [
        (point.period_start, point.response_count, point.application_count, point.response_rate)
        for point in points
    ] == [
        ("2026-07-01", 1, 1, 1.0),
    ]


def test_response_rate_trend_api_returns_deterministic_points(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-1",
            first_seen_at="2026-07-01T09:00:00+00:00",
            responded=True,
        )
        insert_application(
            connection,
            application_id="app-2",
            first_seen_at="2026-07-01T10:00:00+00:00",
            responded=False,
        )

    response = create_test_client(database_path).get("/metrics/response-rate-trend")

    assert response.status_code == 200
    assert response.json() == {
        "points": [
            {
                "period_start": "2026-07-01",
                "response_count": 1,
                "application_count": 2,
                "response_rate": 0.5,
            }
        ]
    }


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


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    first_seen_at: str,
    responded: bool,
    source: str = "linkedin",
) -> None:
    applied_email_id = f"{application_id}-applied-email"
    insert_raw_email(connection, email_id=applied_email_id, sent_at=first_seen_at)
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=f"{application_id} Corp",
        role_title="Software Engineer",
        source=source,
        first_seen_at=first_seen_at,
        current_status="in_review" if responded else "applied",
        last_activity_at=first_seen_at,
        created_at=first_seen_at,
        updated_at=first_seen_at,
        sponsorship="unknown",
        tech_stack=[],
    )
    EventRepository(connection).upsert_event(
        id=f"{application_id}-applied",
        application_id=application_id,
        email_id=applied_email_id,
        event_type="applied",
        event_at=first_seen_at,
    )
    if responded:
        response_email_id = f"{application_id}-response-email"
        insert_raw_email(connection, email_id=response_email_id, sent_at=first_seen_at)
        EventRepository(connection).upsert_event(
            id=f"{application_id}-response",
            application_id=application_id,
            email_id=response_email_id,
            event_type="response",
            event_at=first_seen_at,
        )
    connection.commit()


def insert_raw_email(connection: sqlite3.Connection, *, email_id: str, sent_at: str) -> None:
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
            sent_at,
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            sent_at,
        ),
    )
