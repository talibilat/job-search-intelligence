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


def test_attention_is_unique_by_company_and_persists_done_state(tmp_path: Path) -> None:
    database_path = _migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        _insert_interview(
            connection,
            application_id="acme-current",
            company="Acme",
            event_at="2026-07-10T09:00:00+00:00",
        )
        _insert_interview(
            connection,
            application_id="acme-old",
            company="ACME",
            event_at="2026-06-01T09:00:00+00:00",
        )
        _insert_interview(
            connection,
            application_id="beta",
            company="Beta",
            event_at="2026-07-01T09:00:00+00:00",
        )

    client = _client(database_path)
    beta_done = client.put("/attention/interviews/beta-interview/complete")
    assert beta_done.status_code == 200

    response = client.get("/attention")
    assert response.status_code == 200
    body = response.json()
    assert body["unique_interviewed_company_count"] == 2
    assert [item["company"] for item in body["prepare"]] == ["Acme"]
    assert [item["company"] for item in body["interviewed"]] == ["Acme", "Beta"]
    assert [item["company"] for item in body["follow_up"]] == ["Beta"]

    acme_done = client.put("/attention/interviews/acme-current-interview/complete")
    assert acme_done.status_code == 200
    repeated = client.put("/attention/interviews/acme-current-interview/complete")
    assert repeated.status_code == 200
    assert repeated.json()["completed_at"] == acme_done.json()["completed_at"]

    after = client.get("/attention").json()
    assert after["prepare"] == []
    assert after["unique_interviewed_company_count"] == 2


def test_complete_unknown_interview_returns_typed_not_found(tmp_path: Path) -> None:
    response = _client(_migrated_database(tmp_path)).put("/attention/interviews/missing/complete")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Interview task was not found.",
            "details": [],
        }
    }


def _client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        sync_on_open=False,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def _insert_interview(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str,
    event_at: str,
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=company,
        role_title="Lead AI Developer",
        source="linkedin",
        first_seen_at=event_at,
        current_status="interview",
        last_activity_at=event_at,
        created_at=event_at,
        updated_at=event_at,
        sponsorship="unknown",
        tech_stack=[],
    )
    email_id = f"{application_id}-email"
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{application_id}",
            "jobs@example.test",
            "applicant@example.test",
            "Interview invitation",
            event_at,
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            event_at,
        ),
    )
    EventRepository(connection).upsert_event(
        id=f"{application_id}-interview",
        application_id=application_id,
        email_id=email_id,
        event_type="interview_scheduled",
        event_at=event_at,
    )
    connection.commit()
