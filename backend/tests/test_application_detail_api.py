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


def test_list_applications_returns_application_records(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="application-older",
            first_seen_at="2026-06-01T09:00:00+00:00",
            last_activity_at="2026-06-03T10:00:00+00:00",
            created_at="2026-06-01T09:01:00+00:00",
            updated_at="2026-06-03T10:01:00+00:00",
        )
        insert_application(connection, application_id="application-newer")

    client = create_test_client(database_path)

    response = client.get("/applications")

    assert response.status_code == 200
    records = response.json()
    assert [record["id"] for record in records] == [
        "application-newer",
        "application-older",
    ]
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["tech_stack"] == ["Python", "FastAPI"]


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ("status=interview", ["application-remote"]),
        ("source=company_site", ["application-onsite"]),
        ("sponsorship=offered", ["application-offered"]),
        ("work_mode=remote", ["application-offered", "application-remote"]),
    ],
)
def test_list_applications_applies_enum_filters(
    tmp_path: Path,
    query: str,
    expected_ids: list[str],
) -> None:
    database_path = database_with_filter_fixture(tmp_path)
    client = create_test_client(database_path)

    response = client.get(f"/applications?{query}")

    assert response.status_code == 200
    assert [record["id"] for record in response.json()] == expected_ids


def test_list_applications_applies_date_role_and_salary_band_filters(tmp_path: Path) -> None:
    database_path = database_with_filter_fixture(tmp_path)
    client = create_test_client(database_path)

    response = client.get(
        "/applications"
        "?first_seen_from=2026-07-01T00:00:00Z"
        "&first_seen_to=2026-07-31T23:59:59Z"
        "&role=backend"
        "&salary_min=125000"
        "&salary_max=170000",
    )

    assert response.status_code == 200
    assert [record["id"] for record in response.json()] == ["application-offered"]


def test_list_applications_rejects_inverted_salary_band(tmp_path: Path) -> None:
    database_path = database_with_filter_fixture(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/applications?salary_min=200000&salary_max=100000")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "field": "query.salary_min",
                    "message": "salary_min must be less than or equal to salary_max.",
                    "type": "value_error",
                }
            ],
        }
    }


def test_list_applications_rejects_naive_first_seen_filter(tmp_path: Path) -> None:
    database_path = database_with_filter_fixture(tmp_path)
    client = create_test_client(database_path)

    response = client.get("/applications?first_seen_to=2026-07-01T09:00:00")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "field": "query.first_seen_to",
                    "message": "first_seen_to must include a timezone offset.",
                    "type": "timezone_aware",
                }
            ],
        }
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


def test_list_applications_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/applications"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["items"]["$ref"] == "#/components/schemas/ApplicationRecord"


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


def test_application_repository_list_returns_filtered_records(tmp_path: Path) -> None:
    database_path = database_with_filter_fixture(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = ApplicationRepository(connection)

        records = repository.list_applications(
            current_status="applied",
            source="linkedin",
            sponsorship="offered",
            first_seen_from="2026-07-01T00:00:00+00:00",
            first_seen_to="2026-07-31T23:59:59+00:00",
            role="backend",
            salary_min=125000,
            salary_max=170000,
            work_mode="remote",
        )

    assert [record.id for record in records] == ["application-offered"]


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


def test_application_detail_service_lists_applications(tmp_path: Path) -> None:
    from app.services.applications import ApplicationDetailService

    database_path = database_with_filter_fixture(tmp_path)
    with sqlite3.connect(database_path) as connection:
        service = ApplicationDetailService(ApplicationRepository(connection))

        records = service.list_applications(status="interview")

    assert [record.id for record in records] == ["application-remote"]


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


def database_with_filter_fixture(tmp_path: Path) -> Path:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="application-remote",
            role_title="Backend Engineer",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="interview",
            last_activity_at="2026-07-03T10:00:00+00:00",
            salary_min=100000,
            salary_max=120000,
            work_mode="remote",
            sponsorship="unknown",
        )
        insert_application(
            connection,
            application_id="application-onsite",
            company="Beta LLC",
            role_title="Frontend Engineer",
            source="company_site",
            first_seen_at="2026-06-15T09:00:00+00:00",
            current_status="rejected",
            last_activity_at="2026-06-17T10:00:00+00:00",
            salary_min=70000,
            salary_max=90000,
            work_mode="onsite",
            sponsorship="not_offered",
        )
        insert_application(
            connection,
            application_id="application-offered",
            company="Gamma Inc",
            role_title="Senior Backend Engineer",
            source="linkedin",
            first_seen_at="2026-07-10T09:00:00+00:00",
            current_status="applied",
            last_activity_at="2026-07-11T10:00:00+00:00",
            salary_min=130000,
            salary_max=160000,
            work_mode="remote",
            sponsorship="offered",
        )
    return database_path


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str = "Acme Corp",
    role_title: str = "Software Engineer",
    source: str = "linkedin",
    first_seen_at: str = "2026-07-01T09:00:00+00:00",
    current_status: str = "interview",
    last_activity_at: str = "2026-07-03T10:00:00+00:00",
    created_at: str = "2026-07-01T09:01:00+00:00",
    updated_at: str = "2026-07-03T10:01:00+00:00",
    salary_min: int | None = 100000,
    salary_max: int | None = 120000,
    currency: str | None = "USD",
    location: str | None = "Remote",
    work_mode: str | None = "remote",
    seniority: str | None = "senior",
    sponsorship: str = "unknown",
    tech_stack: list[str] | None = None,
    manual_lock: bool = False,
) -> None:
    repository = ApplicationRepository(connection)
    repository.upsert_application(
        id=application_id,
        company=company,
        role_title=role_title,
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
        last_activity_at=last_activity_at,
        created_at=created_at,
        updated_at=updated_at,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        location=location,
        work_mode=work_mode,
        seniority=seniority,
        sponsorship=sponsorship,
        tech_stack=tech_stack or ["Python", "FastAPI"],
        manual_lock=manual_lock,
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
