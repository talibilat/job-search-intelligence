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


def test_metrics_breakdown_returns_source_rows(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application_with_events(
            connection,
            "app-linkedin",
            "linkedin",
            ("applied", "response"),
        )
        insert_application_with_events(connection, "app-company", "company_site", ("applied",))
        insert_application_with_events(
            connection,
            "app-company-offer",
            "company_site",
            ("applied", "interview_scheduled", "offer"),
        )

    response = create_test_client(database_path).get("/metrics/breakdown?dimension=source")

    assert response.status_code == 200
    assert response.json() == {
        "dimension": "source",
        "rows": [
            {
                "dimension": "source",
                "value": "company_site",
                "application_count": 2,
                "response_count": 1,
                "interview_count": 1,
                "offer_count": 1,
            },
            {
                "dimension": "source",
                "value": "linkedin",
                "application_count": 1,
                "response_count": 1,
                "interview_count": 0,
                "offer_count": 0,
            },
        ],
    }


def test_metrics_breakdown_composes_status_filter(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application_with_events(
            connection,
            "app-linkedin",
            "linkedin",
            ("applied", "response"),
        )
        insert_application_with_events(
            connection,
            "app-company-interview",
            "company_site",
            ("applied", "interview_scheduled"),
            current_status="interview",
        )

    response = create_test_client(database_path).get(
        "/metrics/breakdown?dimension=source&status=interview",
    )

    assert response.status_code == 200
    assert response.json() == {
        "dimension": "source",
        "rows": [
            {
                "dimension": "source",
                "value": "company_site",
                "application_count": 1,
                "response_count": 1,
                "interview_count": 1,
                "offer_count": 0,
            },
        ],
    }


def test_metrics_breakdown_rejects_invalid_filter_ranges(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)

    response = create_test_client(database_path).get(
        "/metrics/breakdown?dimension=source&salary_min=200000&salary_max=100000",
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "field": "query.salary_min",
                    "message": "salary_min must be less than or equal to salary_max",
                    "type": "value_error",
                },
            ],
        },
    }


def test_metrics_breakdown_role_filter_treats_like_wildcards_literally(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application_with_events(
            connection,
            "app-percent-literal",
            "linkedin",
            ("applied",),
            role_title="C++ 100% Systems Engineer",
        )
        insert_application_with_events(
            connection,
            "app-percent-wildcard",
            "company_site",
            ("applied",),
            role_title="C++ 1000 Systems Engineer",
        )

    response = create_test_client(database_path).get(
        "/metrics/breakdown?dimension=source&role=100%25",
    )

    assert response.status_code == 200
    assert response.json() == {
        "dimension": "source",
        "rows": [
            {
                "dimension": "source",
                "value": "linkedin",
                "application_count": 1,
                "response_count": 0,
                "interview_count": 0,
                "offer_count": 0,
            },
        ],
    }


def test_metrics_breakdown_buckets_seniority_conversion_rows(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application_with_events(
            connection,
            "app-junior",
            "linkedin",
            ("applied",),
            seniority="Junior Engineer",
        )
        insert_application_with_events(
            connection,
            "app-mid",
            "linkedin",
            ("applied", "response"),
            seniority="Mid-level",
        )
        insert_application_with_events(
            connection,
            "app-senior",
            "company_site",
            ("applied", "interview_scheduled"),
            seniority="Sr. Software Engineer",
        )
        insert_application_with_events(
            connection,
            "app-lead",
            "referral",
            ("applied", "interview_scheduled", "offer"),
            seniority="Principal / Staff Lead",
        )
        insert_application_with_events(
            connection,
            "app-unknown",
            "other",
            ("applied",),
            seniority="",
        )

    response = create_test_client(database_path).get(
        "/metrics/breakdown?dimension=seniority",
    )

    assert response.status_code == 200
    assert response.json() == {
        "dimension": "seniority",
        "rows": [
            {
                "dimension": "seniority",
                "value": "junior",
                "application_count": 1,
                "response_count": 0,
                "interview_count": 0,
                "offer_count": 0,
            },
            {
                "dimension": "seniority",
                "value": "mid",
                "application_count": 1,
                "response_count": 1,
                "interview_count": 0,
                "offer_count": 0,
            },
            {
                "dimension": "seniority",
                "value": "senior",
                "application_count": 1,
                "response_count": 1,
                "interview_count": 1,
                "offer_count": 0,
            },
            {
                "dimension": "seniority",
                "value": "lead",
                "application_count": 1,
                "response_count": 1,
                "interview_count": 1,
                "offer_count": 1,
            },
            {
                "dimension": "seniority",
                "value": "unknown",
                "application_count": 1,
                "response_count": 0,
                "interview_count": 0,
                "offer_count": 0,
            },
        ],
    }


def test_metrics_breakdown_endpoint_is_documented_in_openapi() -> None:
    response = TestClient(create_app()).get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/breakdown"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    validation_schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsBreakdownResponse"
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


def insert_application_with_events(
    connection: sqlite3.Connection,
    application_id: str,
    source: str,
    event_types: tuple[str, ...],
    *,
    current_status: str = "applied",
    role_title: str = "Software Engineer",
    seniority: str | None = None,
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=f"{application_id} Corp",
        role_title=role_title,
        source=source,
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status=current_status,
        last_activity_at="2026-07-01T09:00:00+00:00",
        created_at="2026-07-01T09:01:00+00:00",
        updated_at="2026-07-01T09:01:00+00:00",
        sponsorship="unknown",
        seniority=seniority,
        tech_stack=[],
    )
    for index, event_type in enumerate(event_types):
        email_id = f"{application_id}-email-{index}"
        insert_raw_email(connection, email_id=email_id)
        EventRepository(connection).upsert_event(
            id=f"{application_id}-event-{index}",
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=f"2026-07-{index + 1:02d}T09:00:00+00:00",
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
