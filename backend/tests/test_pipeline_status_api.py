from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def migrate_database(database_path: Path) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")


def make_client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def insert_connection(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO email_connections (
            provider, account_id, display_email,
            credential_ref_kind, credential_ref_provider, credential_ref_name,
            granted_scopes, connected_at, credential_expires_at,
            reauth_required, updated_at
        ) VALUES (
            'gmail', 'me@example.com', 'me@example.com',
            'oauth_token', 'gmail', 'gmail-token',
            '["https://www.googleapis.com/auth/gmail.readonly"]',
            '2026-07-01T09:00:00+00:00', NULL,
            0, '2026-07-01T09:00:00+00:00'
        )
        """
    )


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    retention_state: str = "metadata_only",
    body_text: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at,
            body_text, body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, 'jobs@example.com', 'me@example.com', 'Subject',
                  '2026-07-01T10:00:00+00:00', ?, ?, '[]', 'gmail',
                  '2026-07-02T10:00:00+00:00')
        """,
        (email_id, f"thread-{email_id}", body_text, retention_state),
    )


def test_pipeline_status_without_connection_returns_connect_gmail(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate_database(database_path)
    client = make_client(database_path)

    response = client.get("/pipeline/status")

    assert response.status_code == 200
    data = response.json()
    assert data["gmail_connected"] is False
    assert data["next_action"] == "connect_gmail"
    assert data["counts"]["raw_email_count"] == 0
    assert data["backfill_state"] == "not_started"
    assert data["incremental_sync_ready"] is False


def test_pipeline_status_with_incomplete_backfill_says_continue(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate_database(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection)
        insert_raw_email(connection, "email-1")
        insert_raw_email(
            connection,
            "email-2",
            retention_state="retained",
            body_text="We received your application.",
        )
        connection.execute(
            """
            INSERT INTO email_filter_decisions (
                email_id, strategy, outcome, reason, decided_at
            ) VALUES
                ('email-1', 'broad_job_search', 'rejected', 'no_filter_signal',
                 '2026-07-02T10:00:00+00:00'),
                ('email-2', 'broad_job_search', 'candidate',
                 'sender_domain:example.com', '2026-07-02T10:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO email_backfill_state (
                provider, account_id, status, next_page_token,
                processed_page_count, processed_message_count,
                sync_cursor, cursor_issued_at, started_at, updated_at,
                completed_at, last_error
            ) VALUES (
                'gmail', 'me@example.com', 'running', 'page-token-2',
                3, 13, NULL, NULL,
                '2026-07-01T09:00:00+00:00', '2026-07-02T10:00:00+00:00',
                NULL, NULL
            )
            """
        )
    client = make_client(database_path)

    response = client.get("/pipeline/status")

    assert response.status_code == 200
    data = response.json()
    assert data["gmail_connected"] is True
    assert data["account_display"] == "me@example.com"
    assert data["backfill_state"] == "running"
    assert data["backfill_complete"] is False
    assert data["backfill_pages_processed"] == 3
    assert data["backfill_messages_processed"] == 13
    assert data["incremental_sync_ready"] is False
    assert data["counts"]["raw_email_count"] == 2
    assert data["counts"]["retained_body_count"] == 1
    assert data["counts"]["filter_candidate_count"] == 1
    assert data["counts"]["filter_rejected_count"] == 1
    assert data["next_action"] == "continue_backfill"
    assert "backfill" in data["next_action_reason"].lower()


def test_pipeline_status_with_unclassified_candidates_says_run_classification(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate_database(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection)
        insert_raw_email(
            connection,
            "email-1",
            retention_state="retained",
            body_text="We received your application.",
        )
        connection.execute(
            """
            INSERT INTO email_backfill_state (
                provider, account_id, status, next_page_token,
                processed_page_count, processed_message_count,
                sync_cursor, cursor_issued_at, started_at, updated_at,
                completed_at, last_error
            ) VALUES (
                'gmail', 'me@example.com', 'completed', NULL,
                5, 50, 'cursor-1', '2026-07-02T10:00:00+00:00',
                '2026-07-01T09:00:00+00:00', '2026-07-02T10:00:00+00:00',
                '2026-07-02T10:00:00+00:00', NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider, account_id, sync_cursor, cursor_issued_at,
                in_progress_mode, next_page_token, updated_at
            ) VALUES (
                'gmail', 'me@example.com', 'cursor-1',
                '2026-07-02T10:00:00+00:00', NULL, NULL,
                '2026-07-02T10:00:00+00:00'
            )
            """
        )
    client = make_client(database_path)

    response = client.get("/pipeline/status")

    assert response.status_code == 200
    data = response.json()
    assert data["backfill_complete"] is True
    assert data["incremental_sync_ready"] is True
    assert data["unclassified_retained_count"] == 1
    assert data["next_action"] == "run_classification"


def test_pipeline_status_never_exposes_email_content(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate_database(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_connection(connection)
        insert_raw_email(
            connection,
            "email-1",
            retention_state="retained",
            body_text="Private body text that must stay local.",
        )
    client = make_client(database_path)

    response = client.get("/pipeline/status")

    assert response.status_code == 200
    assert "Private body" not in response.text
    assert "Subject" not in response.text
    assert "jobs@example.com" not in response.text
