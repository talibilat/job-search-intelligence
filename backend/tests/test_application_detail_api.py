from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository
from app.db.repositories.event import EventRepository
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_get_application_detail_returns_application_record(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="application-42")

    client = create_test_client(database_path)

    response = client.get("/applications/application-42")

    assert response.status_code == 200
    assert response.json() == {
        "id": "application-42",
        "company": "Acme Corp",
        "role_title": "Software Engineer",
        "source": "linkedin",
        "first_seen_at": "2026-07-01T09:00:00Z",
        "current_status": "interview",
        "salary_min": 100000,
        "salary_max": 120000,
        "currency": "USD",
        "location": "Remote",
        "work_mode": "remote",
        "seniority": "senior",
        "sponsorship": "unknown",
        "tech_stack": ["Python", "FastAPI"],
        "last_activity_at": "2026-07-03T10:00:00Z",
        "manual_lock": False,
        "created_at": "2026-07-01T09:01:00Z",
        "updated_at": "2026-07-03T10:01:00Z",
    }


def test_get_application_detail_returns_typed_not_found(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/applications/missing-application")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Application not found.",
            "details": [],
        }
    }


def test_get_application_events_returns_ordered_timeline(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="application-42")
        insert_raw_email(connection, email_id="email-1")
        insert_raw_email(connection, email_id="email-2")
        event_repository = EventRepository(connection)
        event_repository.upsert_event(
            id="event-2",
            application_id="application-42",
            email_id="email-2",
            event_type="rejection",
            event_at="2026-07-03T10:00:00+00:00",
            extract_note="Rejected after review.",
        )
        event_repository.upsert_event(
            id="event-1",
            application_id="application-42",
            email_id="email-1",
            event_type="applied",
            event_at="2026-07-01T09:00:00+00:00",
            extract_note="Application confirmation received.",
        )

    client = create_test_client(database_path)

    response = client.get("/applications/application-42/events")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "event-1",
            "application_id": "application-42",
            "email_id": "email-1",
            "event_type": "applied",
            "event_at": "2026-07-01T09:00:00Z",
            "extract_note": "Application confirmation received.",
            "extracted_status": None,
            "email_sent_at": "2026-07-01T09:00:00Z",
            "classification_classified_at": None,
        },
        {
            "id": "event-2",
            "application_id": "application-42",
            "email_id": "email-2",
            "event_type": "rejection",
            "event_at": "2026-07-03T10:00:00Z",
            "extract_note": "Rejected after review.",
            "extracted_status": None,
            "email_sent_at": "2026-07-01T09:00:00Z",
            "classification_classified_at": None,
        },
    ]


def test_get_application_events_returns_empty_timeline(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="application-without-events")

    client = create_test_client(database_path)

    response = client.get("/applications/application-without-events/events")

    assert response.status_code == 200
    assert response.json() == []


def test_get_application_events_returns_typed_not_found(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/applications/missing-application/events")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Application not found.",
            "details": [],
        }
    }


def test_get_application_detail_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/applications/{id}"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    not_found_schema = operation["responses"]["404"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/ApplicationRecord"
    assert not_found_schema["$ref"] == "#/components/schemas/ApiErrorResponse"


def test_application_events_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/applications/{id}/events"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    not_found_schema = operation["responses"]["404"]["content"]["application/json"]["schema"]
    assert success_schema["items"]["$ref"] == "#/components/schemas/ApplicationEventRecord"
    assert not_found_schema["$ref"] == "#/components/schemas/ApiErrorResponse"


def test_application_repository_get_by_id_returns_matching_record(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="application-42")
        repository = ApplicationRepository(connection)

        record = repository.get_by_id("application-42")

    assert record is not None
    assert record.id == "application-42"
    assert record.company == "Acme Corp"
    assert record.tech_stack == ["Python", "FastAPI"]


def test_application_repository_get_by_id_raises_when_applications_table_is_missing() -> None:
    with sqlite3.connect(":memory:") as connection:
        repository = ApplicationRepository(connection)

        with pytest.raises(sqlite3.OperationalError, match="no such table: applications"):
            repository.get_by_id("application-42")


def test_application_detail_service_raises_for_missing_application(tmp_path: Path) -> None:
    from app.services.applications import ApplicationDetailService, ApplicationNotFoundError

    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        service = ApplicationDetailService(ApplicationRepository(connection))

        with pytest.raises(ApplicationNotFoundError):
            service.get_application("missing-application")


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


def insert_application(connection: sqlite3.Connection, *, application_id: str) -> None:
    repository = ApplicationRepository(connection)
    repository.upsert_application(
        id=application_id,
        company="Acme Corp",
        role_title="Software Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="interview",
        last_activity_at="2026-07-03T10:00:00+00:00",
        created_at="2026-07-01T09:01:00+00:00",
        updated_at="2026-07-03T10:01:00+00:00",
        salary_min=100000,
        salary_max=120000,
        currency="USD",
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=["Python", "FastAPI"],
        manual_lock=False,
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
            "2026-07-01T09:00:00+00:00",
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            "2026-07-01T09:01:00+00:00",
        ),
    )
    connection.commit()
