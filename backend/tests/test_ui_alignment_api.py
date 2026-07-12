"""API contract tests for the redesign-facing backend surfaces.

Covers the deterministic endpoints added for the JobTracker redesign:
status counts, the cross-application recent-events feed, connection
listing and disconnect, local sync stats, sync scope estimates, and
persisted insight citations.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.api.auth import get_gmail_secret_store
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository, InsightRepository
from app.db.repositories.event import EventRepository
from app.main import create_app
from app.models import InsightCitation
from app.security import SecretRef
from fastapi.testclient import TestClient
from pydantic import SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class FakeSecretStore:
    def __init__(self) -> None:
        self.deleted: list[SecretRef] = []

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        return None

    async def delete_secret(self, ref: SecretRef) -> None:
        self.deleted.append(ref)


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def create_test_client(
    database_path: Path,
    *,
    secret_store: FakeSecretStore | None = None,
) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        sync_on_open=False,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    if secret_store is not None:
        app.dependency_overrides[get_gmail_secret_store] = lambda: secret_store
    return TestClient(app)


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str = "Acme Corp",
    current_status: str = "interview",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=company,
        role_title="Software Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status=current_status,
        last_activity_at="2026-07-03T10:00:00+00:00",
        created_at="2026-07-01T09:01:00+00:00",
        updated_at="2026-07-03T10:01:00+00:00",
        salary_min=None,
        salary_max=None,
        currency=None,
        location=None,
        work_mode=None,
        seniority=None,
        sponsorship="unknown",
        tech_stack=[],
        manual_lock=False,
    )
    connection.commit()


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    subject: str = "Application update",
    sent_at: str = "2026-07-01T09:00:00+00:00",
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'metadata_only', '[]', 'gmail', ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "applicant@example.test",
            subject,
            sent_at,
            "2026-07-01T09:01:00+00:00",
        ),
    )
    connection.commit()


def insert_connection(
    connection: sqlite3.Connection,
    *,
    account_id: str = "you@example.test",
) -> None:
    connection.execute(
        """
        INSERT INTO email_connections (
            provider, account_id, display_email, credential_ref_kind,
            credential_ref_provider, credential_ref_name, granted_scopes,
            connected_at, credential_expires_at, reauth_required, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?)
        """,
        (
            "gmail",
            account_id,
            account_id,
            "oauth_token",
            "gmail",
            "you-example.test",
            '["https://www.googleapis.com/auth/gmail.readonly"]',
            "2026-07-01T09:00:00+00:00",
            "2026-07-01T09:00:00+00:00",
        ),
    )
    connection.commit()


def test_status_counts_are_zero_filled_and_deterministic(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-1", current_status="interview")
        insert_application(connection, application_id="app-2", current_status="applied")
        insert_application(connection, application_id="app-3", current_status="applied")

    response = create_test_client(database_path).get("/applications/status-counts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["counts"]["applied"] == 2
    assert payload["counts"]["interview"] == 1
    assert payload["counts"]["offer"] == 0
    assert set(payload["counts"]) == {
        "applied",
        "in_review",
        "assessment",
        "interview",
        "offer",
        "rejected",
        "ghosted",
        "withdrawn",
    }


def test_recent_events_feed_spans_applications_newest_first(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-1", company="Acme Corp")
        insert_application(connection, application_id="app-2", company="Beta LLC")
        insert_raw_email(connection, email_id="email-1", subject="Thanks for applying")
        insert_raw_email(connection, email_id="email-2", subject="Interview scheduled")
        events = EventRepository(connection)
        events.upsert_event(
            id="event-1",
            application_id="app-1",
            email_id="email-1",
            event_type="applied",
            event_at="2026-07-01T09:00:00+00:00",
        )
        events.upsert_event(
            id="event-2",
            application_id="app-2",
            email_id="email-2",
            event_type="interview_scheduled",
            event_at="2026-07-05T09:00:00+00:00",
        )

    response = create_test_client(database_path).get("/applications/events/recent?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["event_id"] == "event-2"
    assert payload[0]["company"] == "Beta LLC"
    assert payload[0]["email_subject"] == "Interview scheduled"
    assert "body" not in payload[0]


def test_list_connections_returns_stored_metadata(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection, account_id="you@example.test")

    response = create_test_client(database_path).get("/auth/connections")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["account"]["account_id"] == "you@example.test"
    assert payload[0]["reauth_required"] is False


def test_disconnect_removes_connection_and_credential(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection, account_id="you@example.test")
    secret_store = FakeSecretStore()
    client = create_test_client(database_path, secret_store=secret_store)

    response = client.delete("/auth/connections/gmail/you@example.test")

    assert response.status_code == 200
    assert response.json()["account"]["account_id"] == "you@example.test"
    assert [ref.name for ref in secret_store.deleted] == ["you-example.test"]
    assert client.get("/auth/connections").json() == []

    missing = client.delete("/auth/connections/gmail/you@example.test")
    assert missing.status_code == 404


def test_sync_stats_reports_local_totals(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, email_id="email-1")
        insert_raw_email(connection, email_id="email-2")

    response = create_test_client(database_path).get("/sync/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_raw_emails"] == 2
    assert payload["last_run_at"] is None


def test_sync_estimate_reports_full_backfill_before_history_is_complete(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection)
        insert_raw_email(connection, email_id="email-1")
    client = create_test_client(database_path)

    response = client.get("/sync/estimate?max_age_days=7")

    assert response.status_code == 200
    assert response.json() == {
        "basis": "full_backfill",
        "estimated_message_count": None,
        "total_local_emails": 1,
        "window_end": None,
        "window_start": None,
    }


def test_sync_estimate_reports_full_backfill_for_legacy_cursor_without_backfill(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection)
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider, account_id, sync_cursor, cursor_issued_at, updated_at
            ) VALUES ('gmail', 'you@example.test', 'legacy-cursor', ?, ?)
            """,
            ("2026-07-01T09:00:00+00:00", "2026-07-01T09:00:00+00:00"),
        )
        connection.commit()

    response = create_test_client(database_path).get("/sync/estimate")

    assert response.status_code == 200
    assert response.json()["basis"] == "full_backfill"


def test_sync_estimate_bases_after_history_is_complete(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection)
        insert_raw_email(connection, email_id="email-1", sent_at="2026-07-01T09:00:00+00:00")
        insert_raw_email(connection, email_id="email-2", sent_at="2026-05-01T09:00:00+00:00")
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider, account_id, sync_cursor, cursor_issued_at, updated_at
            ) VALUES ('gmail', 'you@example.test', 'history-current', ?, ?)
            """,
            ("2026-07-01T09:00:00+00:00", "2026-07-01T09:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO email_backfill_state (
                provider, account_id, status, next_page_token,
                processed_page_count, processed_message_count, sync_cursor,
                cursor_issued_at, started_at, updated_at, completed_at, last_error
            ) VALUES (
                'gmail', 'you@example.test', 'completed', NULL,
                1, 2, 'history-current', ?, ?, ?, ?, NULL
            )
            """,
            (
                "2026-07-01T09:00:00+00:00",
                "2026-07-01T09:00:00+00:00",
                "2026-07-01T09:00:00+00:00",
                "2026-07-01T09:00:00+00:00",
            ),
        )
        connection.commit()
    client = create_test_client(database_path)

    incremental = client.get("/sync/estimate").json()
    assert incremental["basis"] == "unknown_incremental"
    assert incremental["estimated_message_count"] is None
    assert incremental["total_local_emails"] == 2

    capped = client.get("/sync/estimate?max_messages=500").json()
    assert capped["basis"] == "message_cap"
    assert capped["estimated_message_count"] == 500

    windowed = client.get(
        "/sync/estimate?since_date=2026-06-01&before_date=2026-08-01",
    ).json()
    assert windowed["basis"] == "unknown_incremental_window"
    assert windowed["estimated_message_count"] is None
    assert windowed["window_start"] == "2026-06-01T00:00:00Z"
    assert windowed["window_end"] == "2026-08-01T00:00:00Z"

    invalid = client.get("/sync/estimate?since_date=2026-08-01&before_date=2026-06-01")
    assert invalid.status_code == 422


def test_insight_citations_round_trip(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = InsightRepository(connection)
        saved = repository.save_generated_insight(
            insight_type="story",
            content="Narrative grounded in [application:app-1].",
            inputs_hash="hash-1",
            model="test-model",
            generated_at=datetime(2026, 7, 10, tzinfo=UTC),
            citations=[
                InsightCitation(
                    citation_id="application:app-1|email:email-1",
                    application_id="app-1",
                    company="Acme Corp",
                    role_title="Software Engineer",
                    email_id="email-1",
                    email_subject="Thanks for applying",
                ),
            ],
        )
        connection.commit()

        assert [citation.application_id for citation in saved.citations] == ["app-1"]
        listed = repository.list_latest_insights(include_stale=True)
        assert listed[0].citations[0].email_subject == "Thanks for applying"
        assert listed[0].citations[0].citation_id == "application:app-1|email:email-1"
