from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_get_metrics_summary_counts_lifetime_and_ghosted_applications(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-silent-old",
            current_status="applied",
            first_seen_at="2020-01-01T09:00:00+00:00",
            last_activity_at="2020-01-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-silent-old-applied",
            application_id="app-silent-old",
            event_type="applied",
            event_at="2020-01-01T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-already-ghosted",
            current_status="ghosted",
            first_seen_at="2020-02-01T09:00:00+00:00",
            last_activity_at="2020-03-17T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-already-ghosted-applied",
            application_id="app-already-ghosted",
            event_type="applied",
            event_at="2020-02-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-already-ghosted",
            application_id="app-already-ghosted",
            event_type="ghost_inferred",
            event_at="2020-03-17T09:00:00+00:00",
            email_id=None,
        )
        insert_application(
            connection,
            application_id="app-responded",
            current_status="in_review",
            first_seen_at="2020-04-01T09:00:00+00:00",
            last_activity_at="2020-04-05T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-responded-applied",
            application_id="app-responded",
            event_type="applied",
            event_at="2020-04-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-responded-response",
            application_id="app-responded",
            event_type="response",
            event_at="2020-04-05T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-not-thresholded",
            current_status="applied",
            first_seen_at="2999-01-01T09:00:00+00:00",
            last_activity_at="2999-01-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-not-thresholded-applied",
            application_id="app-not-thresholded",
            event_type="applied",
            event_at="2999-01-01T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=45)

    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_applications"] == 4
    assert body["distinct_company_count"] == 1
    assert body["ghosted_applications"] == 2
    assert body["rejected_applications"] == 0
    assert body["ghost_threshold_days"] == 45
    assert "evaluated_at" in body
    with sqlite3.connect(database_path) as connection:
        ghost_event_count = connection.execute(
            "SELECT COUNT(*) FROM application_events WHERE event_type = 'ghost_inferred'",
        ).fetchone()[0]
    assert ghost_event_count == 1


def test_get_metrics_summary_returns_distinct_company_count_from_applications(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="application-1",
            company="Acme Corp",
        )
        insert_application(
            connection,
            application_id="application-2",
            company=" acme corp ",
        )
        insert_application(
            connection,
            application_id="application-3",
            company="Beta LLC",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_applications"] == 3
    assert body["distinct_company_count"] == 2
    assert body["ghosted_applications"] == 0


def test_get_metrics_summary_counts_rejected_applications(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="rejected-1", current_status="rejected")
        insert_application(connection, application_id="rejected-2", current_status="rejected")
        insert_application(connection, application_id="interview-1", current_status="interview")

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_applications"] == 3
    assert body["rejected_applications"] == 2


def test_get_metrics_summary_counts_offers_received_from_event_history(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="application-offer",
            current_status="offer",
        )
        insert_event(
            connection,
            event_id="event-offer-first",
            application_id="application-offer",
            event_type="offer",
            event_at="2026-07-02T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="event-offer-follow-up",
            application_id="application-offer",
            event_type="offer",
            event_at="2026-07-03T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="application-status-only",
            current_status="offer",
        )
        insert_application(
            connection,
            application_id="application-rejected",
            current_status="rejected",
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="application-rejected",
            event_type="rejection",
            event_at="2026-07-04T09:00:00+00:00",
        )

    client = create_test_client(database_path, ghost_threshold_days=30)

    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["offers_received"] == 1
    assert body["ghosted_applications"] == 0


def test_metrics_summary_returns_zero_without_applications(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_applications"] == 0
    assert body["distinct_company_count"] == 0
    assert body["offers_received"] == 0
    assert body["ghosted_applications"] == 0
    assert body["rejected_applications"] == 0
    assert body["interview_invitation_count"] == 0
    assert body["average_time_to_first_response"] == {
        "application_count": 0,
        "average_hours": None,
    }
    assert body["ghost_threshold_days"] == 30
    assert "evaluated_at" in body


def test_metrics_summary_returns_average_time_to_first_response(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="fast-response",
            first_seen_at="2026-07-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="fast-response-event",
            application_id="fast-response",
            event_type="response",
            event_at="2026-07-02T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="slow-response",
            first_seen_at="2026-07-01T09:00:00+00:00",
        )
        insert_event(
            connection,
            event_id="slow-response-event",
            application_id="slow-response",
            event_type="interview_scheduled",
            event_at="2026-07-03T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="silent-application",
            first_seen_at="2026-07-01T09:00:00+00:00",
        )

    response = create_test_client(database_path).get("/metrics/summary")

    assert response.status_code == 200
    assert response.json()["average_time_to_first_response"] == {
        "application_count": 2,
        "average_hours": 36.0,
    }


def test_metrics_summary_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/summary"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsSummaryResponse"


def create_test_client(database_path: Path, *, ghost_threshold_days: int = 30) -> TestClient:
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
    current_status: str = "applied",
    first_seen_at: str = "2026-07-01T09:00:00+00:00",
    last_activity_at: str = "2026-07-03T10:00:00+00:00",
    company: str = "Acme Corp",
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
            company,
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
            0,
            first_seen_at,
            first_seen_at,
        ),
    )
    connection.commit()


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    sent_at: str,
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
            "thread-metrics",
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
    connection.commit()


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    event_type: str,
    event_at: str,
    email_id: str | None = None,
) -> None:
    if event_type != "ghost_inferred" and email_id is None:
        email_id = f"email-{event_id}"
    if email_id is not None:
        insert_raw_email(connection, email_id=email_id, sent_at=event_at)
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
