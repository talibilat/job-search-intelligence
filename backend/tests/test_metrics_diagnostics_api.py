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


def test_metrics_diagnostics_returns_segment_comparisons(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_diagnostic_fixture(connection)

    response = create_test_client(database_path).get("/metrics/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_applications"] == 5
    assert payload["baseline_response_count"] == 3
    assert payload["baseline_response_rate"] == 0.6
    assert payload["baseline_success_count"] == 1
    assert payload["baseline_success_rate"] == 0.2
    assert payload["baseline_negative_count"] == 2
    assert payload["baseline_negative_rate"] == 0.4
    assert payload["strongest_response_segments"][0] == {
        "dimension": "source",
        "value": "company_site",
        "application_count": 2,
        "response_count": 2,
        "interview_count": 0,
        "offer_count": 0,
        "success_count": 0,
        "negative_count": 1,
        "response_rate": 1.0,
        "interview_rate": 0.0,
        "offer_rate": 0.0,
        "success_rate": 0.0,
        "negative_rate": 0.5,
        "response_rate_lift": 0.4,
        "success_rate_lift": -0.2,
        "negative_rate_lift": 0.5 - 0.4,
    }
    assert payload["strongest_response_correlate"] == payload["strongest_response_segments"][0]
    assert payload["wasted_effort_segments"] == payload["weakest_response_segments"]
    assert payload["best_roi_source"] == next(
        segment
        for segment in payload["segments"]
        if segment["dimension"] == "source" and segment["value"] == "linkedin"
    )
    assert payload["sponsorship_response_impact"] is not None
    assert payload["sponsorship_response_impact"]["dimension"] == "sponsorship"
    assert payload["successful_application_segments"] == [
        {
            "dimension": "source",
            "value": "linkedin",
            "application_count": 3,
            "response_count": 1,
            "interview_count": 1,
            "offer_count": 1,
            "success_count": 1,
            "negative_count": 1,
            "response_rate": 1 / 3,
            "interview_rate": 1 / 3,
            "offer_rate": 1 / 3,
            "success_rate": 1 / 3,
            "negative_rate": 1 / 3,
            "response_rate_lift": (1 / 3) - 0.6,
            "success_rate_lift": (1 / 3) - 0.2,
            "negative_rate_lift": (1 / 3) - 0.4,
        },
    ]
    assert payload["negative_outcome_segments"] == [
        {
            "dimension": "source",
            "value": "company_site",
            "application_count": 2,
            "response_count": 2,
            "interview_count": 0,
            "offer_count": 0,
            "success_count": 0,
            "negative_count": 1,
            "response_rate": 1.0,
            "interview_rate": 0.0,
            "offer_rate": 0.0,
            "success_rate": 0.0,
            "negative_rate": 0.5,
            "response_rate_lift": 0.4,
            "success_rate_lift": -0.2,
            "negative_rate_lift": 0.5 - 0.4,
        },
    ]
    assert any(
        segment["dimension"] == "source"
        and segment["value"] == "linkedin"
        and segment["application_count"] == 3
        and segment["response_count"] == 1
        for segment in payload["segments"]
    )


def test_metrics_diagnostics_composes_filters(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_diagnostic_fixture(connection)

    response = create_test_client(database_path).get("/metrics/diagnostics?source=linkedin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_applications"] == 3
    assert payload["baseline_response_count"] == 1
    assert payload["baseline_response_rate"] == 1 / 3
    assert payload["baseline_success_count"] == 1
    assert payload["baseline_success_rate"] == 1 / 3
    assert payload["baseline_negative_count"] == 1
    assert payload["baseline_negative_rate"] == 1 / 3
    source_segments = [
        segment for segment in payload["segments"] if segment["dimension"] == "source"
    ]
    assert source_segments == [
        {
            "dimension": "source",
            "value": "linkedin",
            "application_count": 3,
            "response_count": 1,
            "interview_count": 1,
            "offer_count": 1,
            "success_count": 1,
            "negative_count": 1,
            "response_rate": 1 / 3,
            "interview_rate": 1 / 3,
            "offer_rate": 1 / 3,
            "success_rate": 1 / 3,
            "negative_rate": 1 / 3,
            "response_rate_lift": 0.0,
            "success_rate_lift": 0.0,
            "negative_rate_lift": 0.0,
        },
    ]


def test_metrics_diagnostics_endpoint_is_documented_in_openapi() -> None:
    response = TestClient(create_app()).get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/diagnostics"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    validation_schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsDiagnosticsResponse"
    assert validation_schema["$ref"] == "#/components/schemas/ApiErrorResponse"


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


def seed_diagnostic_fixture(connection: sqlite3.Connection) -> None:
    insert_application(
        connection,
        application_id="app-silent",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="applied",
        event_types=("applied",),
    )
    insert_application(
        connection,
        application_id="app-rejected",
        source="company_site",
        first_seen_at="2026-07-01T10:00:00+00:00",
        current_status="rejected",
        event_types=("applied", "rejection"),
    )
    insert_application(
        connection,
        application_id="app-interview-offer",
        source="linkedin",
        first_seen_at="2026-07-01T11:00:00+00:00",
        current_status="offer",
        event_types=("applied", "response", "interview_scheduled", "offer"),
    )
    insert_application(
        connection,
        application_id="app-assessment",
        source="company_site",
        first_seen_at="2026-07-02T09:00:00+00:00",
        current_status="assessment",
        event_types=("applied", "assessment"),
    )
    insert_application(
        connection,
        application_id="app-ghosted",
        source="linkedin",
        first_seen_at="2026-07-02T10:00:00+00:00",
        current_status="ghosted",
        event_types=("applied", "ghost_inferred"),
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    source: str,
    first_seen_at: str,
    current_status: str,
    event_types: tuple[str, ...],
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=f"{application_id} Inc",
        role_title="Software Engineer",
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
        last_activity_at="2026-07-05T09:00:00+00:00",
        created_at=first_seen_at,
        updated_at="2026-07-05T09:00:00+00:00",
        salary_min=120000,
        salary_max=150000,
        currency="USD",
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=["Python"],
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
