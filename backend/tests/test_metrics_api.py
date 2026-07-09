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


def test_metrics_summary_returns_application_counts_by_window(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="week-start",
            first_seen_at="2026-07-13T00:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="week-middle",
            first_seen_at="2026-07-15T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="week-end-boundary",
            first_seen_at="2026-07-20T00:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="month-start",
            first_seen_at="2026-07-01T00:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="month-end-boundary",
            first_seen_at="2026-08-01T00:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="year-start",
            first_seen_at="2026-01-01T00:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="year-end-boundary",
            first_seen_at="2027-01-01T00:00:00+00:00",
        )

    client = create_test_client(database_path)

    response = client.get(
        "/metrics/summary"
        "?anchor_at=2026-07-15T12:00:00Z"
        "&custom_start_at=2026-07-01T00:00:00Z"
        "&custom_end_at=2026-08-01T00:00:00Z",
    )

    assert response.status_code == 200
    assert response.json()["application_windows"] == [
        {
            "window": "week",
            "start_at": "2026-07-13T00:00:00Z",
            "end_at": "2026-07-20T00:00:00Z",
            "application_count": 2,
        },
        {
            "window": "month",
            "start_at": "2026-07-01T00:00:00Z",
            "end_at": "2026-08-01T00:00:00Z",
            "application_count": 4,
        },
        {
            "window": "year",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2027-01-01T00:00:00Z",
            "application_count": 6,
        },
        {
            "window": "custom",
            "start_at": "2026-07-01T00:00:00Z",
            "end_at": "2026-08-01T00:00:00Z",
            "application_count": 4,
        },
    ]


def test_metrics_summary_rejects_naive_anchor_at(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/metrics/summary?anchor_at=2026-07-15T12:00:00")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "field": "query.anchor_at",
                    "message": "anchor_at must include a timezone offset.",
                    "type": "timezone_aware",
                }
            ],
        }
    }


def test_metrics_summary_rejects_incomplete_custom_window(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get(
        "/metrics/summary?anchor_at=2026-07-15T12:00:00Z&custom_start_at=2026-07-01T00:00:00Z",
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {
            "field": "query.custom_end_at",
            "message": "custom_start_at and custom_end_at must be provided together.",
            "type": "missing_custom_window_bound",
        }
    ]


def test_metrics_summary_rejects_inverted_custom_window(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get(
        "/metrics/summary"
        "?anchor_at=2026-07-15T12:00:00Z"
        "&custom_start_at=2026-08-01T00:00:00Z"
        "&custom_end_at=2026-07-01T00:00:00Z",
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {
            "field": "query.custom_start_at",
            "message": "custom_start_at must be earlier than custom_end_at.",
            "type": "value_error",
        }
    ]


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


def test_metrics_funnel_returns_q16_deterministic_stage_counts(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="application-silent",
            current_status="applied",
        )
        insert_event(
            connection,
            event_id="event-silent-applied",
            application_id="application-silent",
            email_id="email-silent-applied",
            event_type="applied",
        )
        insert_application(
            connection,
            application_id="application-screen",
            current_status="in_review",
            source="company_site",
        )
        insert_event(
            connection,
            event_id="event-screen-applied",
            application_id="application-screen",
            email_id="email-screen-applied",
            event_type="applied",
        )
        insert_event(
            connection,
            event_id="event-screen",
            application_id="application-screen",
            email_id="email-screen",
            event_type="response",
        )
        insert_application(
            connection,
            application_id="application-final-rejection",
            current_status="rejected",
        )
        insert_event(
            connection,
            event_id="event-final-applied",
            application_id="application-final-rejection",
            email_id="email-final-applied",
            event_type="applied",
        )
        insert_event(
            connection,
            event_id="event-final-response",
            application_id="application-final-rejection",
            email_id="email-final-response",
            event_type="response",
        )
        insert_event(
            connection,
            event_id="event-final-interview",
            application_id="application-final-rejection",
            email_id="email-final-interview",
            event_type="interview_scheduled",
        )
        insert_event(
            connection,
            event_id="event-final-rejection",
            application_id="application-final-rejection",
            email_id="email-final-rejection",
            event_type="rejection",
        )
        insert_application(
            connection,
            application_id="application-offer",
            current_status="offer",
        )
        insert_event(
            connection,
            event_id="event-offer-applied",
            application_id="application-offer",
            email_id="email-offer-applied",
            event_type="applied",
        )
        insert_event(
            connection,
            event_id="event-offer-response",
            application_id="application-offer",
            email_id="email-offer-response",
            event_type="response",
        )
        insert_event(
            connection,
            event_id="event-offer-interview",
            application_id="application-offer",
            email_id="email-offer-interview",
            event_type="interview_scheduled",
        )
        insert_event(
            connection,
            event_id="event-offer",
            application_id="application-offer",
            email_id="email-offer",
            event_type="offer",
        )
        connection.execute(
            "UPDATE application_events SET event_at = ? WHERE id = ?",
            ("2026-07-04T10:00:00+00:00", "event-offer"),
        )
        connection.execute(
            "UPDATE application_events SET event_at = ? WHERE id = ?",
            ("2026-07-04T10:00:00+00:00", "event-final-rejection"),
        )
        connection.commit()

    client = create_test_client(database_path)

    response = client.get("/metrics/funnel")

    assert response.status_code == 200
    assert response.json() == {
        "stages": [
            {"stage": "applied", "count": 4},
            {"stage": "screen", "count": 3},
            {"stage": "interview", "count": 2},
            {"stage": "final", "count": 0},
            {"stage": "offer", "count": 1},
        ]
    }

    filtered_response = client.get("/metrics/funnel?source=company_site")

    assert filtered_response.status_code == 200
    assert filtered_response.json() == {
        "stages": [
            {"stage": "applied", "count": 1},
            {"stage": "screen", "count": 1},
            {"stage": "interview", "count": 0},
            {"stage": "final", "count": 0},
            {"stage": "offer", "count": 0},
        ]
    }


def test_metrics_funnel_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/funnel"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsFunnelResponse"


def test_metrics_summary_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/summary"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    validation_schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsSummaryResponse"
    assert validation_schema["$ref"] == "#/components/schemas/ApiErrorResponse"


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
    first_seen_at: str = "2026-07-01T09:00:00+00:00",
    source: str = "linkedin",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company="Acme Corp",
        role_title="Software Engineer",
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
        last_activity_at=first_seen_at,
        created_at=first_seen_at,
        updated_at=first_seen_at,
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
