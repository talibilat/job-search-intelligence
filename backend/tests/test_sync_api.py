from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import app.api.sync as sync_api
import pytest
from app.api.sync import (
    ConfiguredEmailSyncRuntime,
    EmailSyncStatusStore,
    get_email_sync_connection_resolver,
    get_email_sync_runtime,
    get_sync_email_provider,
    get_sync_status_store,
)
from app.config import (
    GMAIL_READONLY_SCOPE,
    AppSettings,
    EmailProviderName,
    SecretStoreBackend,
    get_settings,
)
from app.db.repositories import EmailConnectionRepository
from app.main import create_app
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailBodyBatch,
    EmailBodyFetchFailure,
    EmailBodyFetchFailureReason,
    EmailBodyFetchRequest,
    EmailBodySource,
    EmailConnection,
    EmailMessageBody,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProvider,
    EmailProviderAuthError,
    EmailProviderCursor,
    EmailProviderErrorCode,
    EmailProviderTransientError,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef, create_secret_store
from app.services.sync_service import (
    EmailSyncOptions,
    EmailSyncRunState,
    EmailSyncStatus,
    SyncAlreadyRunningError,
)
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class FakeSyncRuntime:
    def __init__(self) -> None:
        self.run_count = 0
        self.last_options: EmailSyncOptions | None = None
        self.status = EmailSyncStatus(state=EmailSyncRunState.IDLE)

    async def run_manual_sync(self, options: EmailSyncOptions | None = None) -> EmailSyncStatus:
        self.run_count += 1
        self.last_options = options
        self.status = EmailSyncStatus(
            state=EmailSyncRunState.SUCCEEDED,
            provider=EmailProviderName.GMAIL,
            account_id="me@example.com",
            mode=EmailSyncMode.FULL_BACKFILL,
            started_at=NOW,
            finished_at=NOW,
            page_count=1,
            message_count=2,
            raw_email_count=2,
            target_message_count=options.max_messages if options is not None else None,
            progress=1,
            recovered_from_expired_cursor=False,
        )
        return self.status

    def current_status(self) -> EmailSyncStatus:
        return self.status

    def recent_email_previews(self, *, limit: int = 10) -> tuple[object, ...]:
        del limit
        return ()


class ProviderErrorSyncRuntime:
    async def run_manual_sync(self, options: EmailSyncOptions | None = None) -> EmailSyncStatus:
        del options
        raise EmailProviderAuthError(
            public_message="Reconnect Gmail to continue syncing.",
            error_code=EmailProviderErrorCode.AUTHORIZATION_REQUIRED,
        )

    def current_status(self) -> EmailSyncStatus:
        return EmailSyncStatus(state=EmailSyncRunState.IDLE)


class FakeMetadataProvider:
    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        return EmailMetadataPage(
            messages=(
                EmailMessageMetadata(
                    ref=EmailMessageRef(
                        account=connection.account,
                        message_id="gmail-msg-1",
                        thread_id="thread-1",
                    ),
                    from_addr=EmailAddress(address="jobs@example.com"),
                    subject="Application received",
                    sent_at=NOW,
                ),
            ),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-next",
                issued_at=NOW,
            ),
        )


class PagingMetadataProvider:
    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        if request.page_token is None:
            return EmailMetadataPage(
                messages=(metadata_message(connection, "gmail-msg-1"),),
                next_page_token="page-2",
            )
        return EmailMetadataPage(
            messages=(metadata_message(connection, "gmail-msg-2"),),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="replacement-cursor",
                issued_at=NOW,
            ),
        )


class ExpiringCursorMetadataProvider:
    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        if request.mode is EmailSyncMode.INCREMENTAL:
            raise EmailSyncCursorExpiredError(public_message="history cursor expired")

        return EmailMetadataPage(
            messages=(metadata_message(connection, "gmail-reconciled-1"),),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-recovered",
                issued_at=NOW,
            ),
        )


class BlockingMetadataProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        del request
        self.started.set()
        await self.release.wait()
        return EmailMetadataPage(
            messages=(metadata_message(connection, "gmail-msg-1"),),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-next",
                issued_at=NOW,
            ),
        )


def test_post_sync_runs_injected_manual_sync_runtime() -> None:
    runtime = FakeSyncRuntime()
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.post("/sync")

    assert response.status_code == 200
    assert runtime.run_count == 1
    assert response.json() == {
        "state": "succeeded",
        "provider": "gmail",
        "account_id": "me@example.com",
        "mode": "full_backfill",
        "started_at": "2026-07-05T12:00:00Z",
        "finished_at": "2026-07-05T12:00:00Z",
        "page_count": 1,
        "message_count": 2,
        "raw_email_count": 2,
        "retained_body_failure_count": 0,
        "target_message_count": None,
        "progress": 1.0,
        "recovered_from_expired_cursor": False,
        "last_error": None,
    }


def test_post_sync_accepts_extraction_limits_for_manual_run() -> None:
    runtime = FakeSyncRuntime()
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.post(
        "/sync",
        json={
            "max_messages": 25,
            "since_date": "2026-01-01",
            "before_date": "2026-07-01",
            "max_age_days": 90,
            "max_pages": 3,
        },
    )

    assert response.status_code == 200
    last_options = runtime.last_options
    assert last_options is not None
    assert last_options.max_messages == 25
    assert last_options.max_pages == 3
    assert last_options.since_date is not None
    assert last_options.since_date.isoformat() == "2026-01-01"
    assert last_options.before_date is not None
    assert last_options.before_date.isoformat() == "2026-07-01"
    assert last_options.max_age_days == 90
    assert response.json()["target_message_count"] == 25
    assert response.json()["progress"] == 1.0


def test_get_sync_status_returns_current_runtime_status() -> None:
    runtime = FakeSyncRuntime()
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json()["state"] == "idle"


def test_get_sync_stats_uses_durable_state_after_process_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider, account_id, sync_cursor, cursor_issued_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "me@example.com",
                "history-1",
                "2026-07-11T09:00:00+00:00",
                "2026-07-11T10:00:00+00:00",
            ),
        )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app.dependency_overrides[get_sync_status_store] = EmailSyncStatusStore

    response = TestClient(app).get("/sync/stats")

    assert response.status_code == 200
    assert response.json()["last_run_at"] == "2026-07-11T10:00:00Z"


def test_post_sync_returns_typed_error_until_gmail_connection_is_configured(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post("/sync")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Gmail connection is not configured yet.",
            "details": [],
        }
    }


def test_post_sync_returns_provider_error_response_from_global_handler() -> None:
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = ProviderErrorSyncRuntime

    client = TestClient(app)

    response = client.post("/sync")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "email_authorization_required",
            "message": "Reconnect Gmail to continue syncing.",
            "details": [
                {
                    "field": "email_provider",
                    "message": "reconnect_email",
                    "type": "user_action",
                }
            ],
        }
    }


def test_post_sync_uses_persisted_gmail_connection_metadata(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        EmailConnectionRepository(connection).save_connection(email_connection())
    provider = FakeMetadataProvider()
    status_store = EmailSyncStatusStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        gmail_page_size=77,
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    app.dependency_overrides[get_sync_status_store] = lambda: status_store
    client = TestClient(app)

    response = client.post("/sync")

    assert response.status_code == 200
    assert response.json()["state"] == "succeeded"
    assert response.json()["message_count"] == 1
    assert len(provider.requests) == 1
    assert provider.requests[0].mode is EmailSyncMode.FULL_BACKFILL
    assert provider.requests[0].page_size == 77

    status_response = client.get("/sync/status")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "succeeded"

    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM raw_emails").fetchone()
        backfill_state = connection.execute(
            """
            SELECT status, processed_page_count, processed_message_count, sync_cursor
            FROM email_backfill_state
            WHERE provider = 'gmail' AND account_id = 'me@example.com'
            """
        ).fetchone()
    assert row == (1,)
    assert tuple(backfill_state) == ("completed", 1, 1, "history-next")


def test_get_sync_recent_emails_returns_safe_metadata_without_body_text(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO raw_emails (
                id,
                public_id,
                thread_id,
                from_addr,
                to_addr,
                subject,
                sent_at,
                body_text,
                body_retention_state,
                labels,
                provider,
                ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gmail-msg-1",
                "0123456789abcdef0123456789abcdef",
                "thread-1",
                "jobs@example.com",
                "me@example.com",
                "Application received",
                "2026-07-05T12:00:00+00:00",
                "Private body must not leave this endpoint",
                "retained",
                '["INBOX"]',
                "gmail",
                "2026-07-05T12:01:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO email_filter_decisions (
                email_id,
                strategy,
                outcome,
                reason,
                decided_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "gmail-msg-1",
                "broad_job_search",
                "candidate",
                "sender_domain:example.com",
                "2026-07-05T12:01:30+00:00",
            ),
        )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get("/sync/recent-emails")

    assert response.status_code == 200
    assert response.json() == [
        {
            "public_id": "0123456789abcdef0123456789abcdef",
            "from_domain": "example.com",
            "to_domains": ["example.com"],
            "subject": "Application received",
            "subject_present": True,
            "sent_at": "2026-07-05T12:00:00Z",
            "body_retention_state": "retained",
            "has_retained_body": True,
            "provider": "gmail",
            "ingested_at": "2026-07-05T12:01:00Z",
            "filter_outcome": "candidate",
            "filter_reason": "sender_domain:example.com",
            "classification_category": None,
            "classification_is_job_related": None,
        }
    ]
    assert "body_text" not in response.text
    assert "Private body" not in response.text
    assert "gmail-msg-1" not in response.text
    assert "thread-1" not in response.text


def test_get_sync_recent_emails_orders_by_sent_at_by_default(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        rows = (
            # Old mailbox message ingested most recently (historical backfill).
            ("gmail-old", "2026-01-01T09:00:00+00:00", "2026-07-05T12:00:00+00:00"),
            # New mailbox message ingested earlier.
            ("gmail-new", "2026-07-01T09:00:00+00:00", "2026-07-02T12:00:00+00:00"),
        )
        for index, (email_id, sent_at, ingested_at) in enumerate(rows):
            connection.execute(
                """
                INSERT INTO raw_emails (
                    id, public_id, thread_id, from_addr, to_addr, subject, sent_at,
                    body_text, body_retention_state, labels, provider, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'metadata_only', '[]', 'gmail', ?)
                """,
                (
                    email_id,
                    f"{index:032x}",
                    f"thread-{email_id}",
                    "a@example.com",
                    "b@example.com",
                    "Subject",
                    sent_at,
                    ingested_at,
                ),
            )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    default_response = client.get("/sync/recent-emails")
    assert default_response.status_code == 200
    assert [email["sent_at"] for email in default_response.json()] == [
        "2026-07-01T09:00:00Z",
        "2026-01-01T09:00:00Z",
    ]

    sent_response = client.get("/sync/recent-emails?order=sent_at")
    assert [email["sent_at"] for email in sent_response.json()] == [
        "2026-07-01T09:00:00Z",
        "2026-01-01T09:00:00Z",
    ]

    ingested_response = client.get("/sync/recent-emails?order=ingested_at")
    assert [email["sent_at"] for email in ingested_response.json()] == [
        "2026-01-01T09:00:00Z",
        "2026-07-01T09:00:00Z",
    ]


def test_incremental_sync_applies_limits_without_provider_date_filters(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        EmailConnectionRepository(connection).save_connection(email_connection())
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider,
                account_id,
                sync_cursor,
                cursor_issued_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "me@example.com",
                "history-current",
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO email_backfill_state (
                provider,
                account_id,
                status,
                processed_page_count,
                processed_message_count,
                sync_cursor,
                cursor_issued_at,
                started_at,
                updated_at,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "me@example.com",
                "completed",
                1,
                1,
                "history-current",
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    provider = FakeMetadataProvider()
    status_store = EmailSyncStatusStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        gmail_page_size=77,
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    app.dependency_overrides[get_sync_status_store] = lambda: status_store
    client = TestClient(app)

    response = client.post(
        "/sync",
        json={
            "max_messages": 12,
            "since_date": "2026-01-01",
            "before_date": "2026-07-01",
            "max_pages": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["target_message_count"] == 12
    assert response.json()["message_count"] == 0
    assert len(provider.requests) == 1
    assert provider.requests[0].page_size == 12
    assert provider.requests[0].since_date is None
    assert provider.requests[0].before_date is None


def test_bounded_first_sync_runs_complete_unbounded_backfill(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    provider = PagingMetadataProvider()
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        gmail_page_size=77,
    )
    runtime = ConfiguredEmailSyncRuntime(
        settings=settings,
        email_provider=cast(EmailProvider, provider),
        connection_resolver=email_connection,
        status_store=EmailSyncStatusStore(),
    )

    status = asyncio.run(
        runtime.run_manual_sync(EmailSyncOptions(max_age_days=7, max_messages=1)),
    )

    assert status.state is EmailSyncRunState.SUCCEEDED
    assert [request.page_token for request in provider.requests] == [None, "page-2"]
    assert all(request.since_date is None for request in provider.requests)
    assert all(request.before_date is None for request in provider.requests)
    assert all(request.page_size == settings.gmail_page_size for request in provider.requests)
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT sync_cursor FROM email_sync_state WHERE provider = ? AND account_id = ?",
            ("gmail", "me@example.com"),
        ).fetchone()
    assert row == ("replacement-cursor",)


def test_sync_marks_connection_for_reauthorization_after_provider_auth_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    connection = email_connection()
    with sqlite3.connect(database_path) as sqlite_connection:
        EmailConnectionRepository(sqlite_connection).save_connection(connection)

    class AuthFailureProvider:
        async def list_message_metadata(self, *_: object) -> object:
            raise EmailProviderAuthError(public_message="Gmail token exchange failed.")

    runtime = ConfiguredEmailSyncRuntime(
        settings=AppSettings(_env_file=None, database_url=f"sqlite+aiosqlite:///{database_path}"),
        email_provider=cast(EmailProvider, AuthFailureProvider()),
        connection_resolver=lambda: connection,
        status_store=EmailSyncStatusStore(),
    )

    with pytest.raises(EmailProviderAuthError):
        asyncio.run(runtime.run_manual_sync())

    with sqlite3.connect(database_path) as sqlite_connection:
        marked = EmailConnectionRepository(sqlite_connection).fetch_connection_metadata(
            connection.account
        )
    assert marked is not None
    assert marked.reauth_required is True


def test_cursor_without_completed_backfill_runs_lifetime_backfill(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider, account_id, sync_cursor, cursor_issued_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "me@example.com",
                "legacy-cursor",
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    provider = PagingMetadataProvider()
    runtime = ConfiguredEmailSyncRuntime(
        settings=AppSettings(
            _env_file=None,
            database_url=f"sqlite+aiosqlite:///{database_path}",
            gmail_page_size=77,
        ),
        email_provider=cast(EmailProvider, provider),
        connection_resolver=email_connection,
        status_store=EmailSyncStatusStore(),
    )

    status = asyncio.run(runtime.run_manual_sync(EmailSyncOptions(max_messages=1)))

    assert status.state is EmailSyncRunState.SUCCEEDED
    assert [request.mode for request in provider.requests] == [
        EmailSyncMode.FULL_BACKFILL,
        EmailSyncMode.FULL_BACKFILL,
    ]
    assert [request.page_token for request in provider.requests] == [None, "page-2"]


def test_default_sync_email_provider_uses_configured_secret_store(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        secret_store_backend=SecretStoreBackend.FERNET,
        fernet_key_file=tmp_path / "fernet.key",
        data_dir=tmp_path,
    )
    provider = get_sync_email_provider(settings, create_secret_store(settings))

    with pytest.raises(EmailProviderAuthError) as error_info:
        asyncio.run(
            provider.list_message_metadata(
                email_connection(),
                EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=1),
            )
        )

    assert error_info.value.public_message == "Gmail authorization is required"


def test_post_sync_recovers_expired_incremental_cursor(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO email_sync_state (
                provider,
                account_id,
                sync_cursor,
                cursor_issued_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "me@example.com",
                "history-expired",
                "2026-07-04T12:00:00+00:00",
                "2026-07-04T12:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO email_backfill_state (
                provider,
                account_id,
                status,
                processed_page_count,
                processed_message_count,
                sync_cursor,
                cursor_issued_at,
                started_at,
                updated_at,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "me@example.com",
                "completed",
                1,
                1,
                "history-expired",
                "2026-07-04T12:00:00+00:00",
                "2026-07-04T12:00:00+00:00",
                "2026-07-04T12:00:00+00:00",
                "2026-07-04T12:00:00+00:00",
            ),
        )
    provider = ExpiringCursorMetadataProvider()
    status_store = EmailSyncStatusStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    app.dependency_overrides[get_email_sync_connection_resolver] = lambda: email_connection
    app.dependency_overrides[get_sync_status_store] = lambda: status_store
    client = TestClient(app)

    response = client.post("/sync")

    assert response.status_code == 200
    assert response.json()["state"] == "succeeded"
    assert response.json()["mode"] == "full_backfill"
    assert response.json()["recovered_from_expired_cursor"] is True
    assert [request.mode for request in provider.requests] == [
        EmailSyncMode.INCREMENTAL,
        EmailSyncMode.FULL_BACKFILL,
    ]


def test_configured_runtime_rejects_concurrent_manual_syncs(tmp_path: Path) -> None:
    async def run_test() -> None:
        database_path = tmp_path / "jobtracker.sqlite3"
        create_sync_tables(database_path)
        provider = BlockingMetadataProvider()
        runtime = ConfiguredEmailSyncRuntime(
            settings=AppSettings(
                _env_file=None,
                database_url=f"sqlite+aiosqlite:///{database_path}",
            ),
            email_provider=cast(EmailProvider, provider),
            connection_resolver=email_connection,
            status_store=EmailSyncStatusStore(),
        )

        first_run = asyncio.create_task(runtime.run_manual_sync())
        await provider.started.wait()

        with pytest.raises(SyncAlreadyRunningError):
            await asyncio.wait_for(runtime.run_manual_sync(), timeout=0.1)

        provider.release.set()
        await first_run

    asyncio.run(run_test())


def test_configured_sync_job_skips_when_gmail_connection_is_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        secret_store_backend=SecretStoreBackend.FERNET,
        fernet_key_file=tmp_path / "fernet.key",
        data_dir=tmp_path,
    )
    status_store = EmailSyncStatusStore()
    monkeypatch.setattr(sync_api, "get_sync_status_store", lambda: status_store)

    async def run_sync_job() -> None:
        await sync_api.create_configured_sync_job(settings)()

    asyncio.run(run_sync_job())

    assert status_store.current_status().state is EmailSyncRunState.IDLE


def test_configured_sync_job_absorbs_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingSyncRuntime:
        async def run_manual_sync(self) -> None:
            raise EmailProviderAuthError(
                public_message="Reconnect Gmail to continue syncing."
            )

    monkeypatch.setattr(
        sync_api,
        "build_configured_email_sync_runtime",
        lambda settings: FailingSyncRuntime(),
    )

    asyncio.run(sync_api.create_configured_sync_job(AppSettings(_env_file=None))())


def test_get_paginated_sync_emails_returns_stable_page(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        for index in range(23):
            insert_raw_email_row(
                connection,
                message_id=f"gmail-msg-{index:02d}",
                public_id=f"{index:032x}",
                sent_at=NOW - timedelta(days=index),
            )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get(
        "/sync/emails",
        params={
            "page": 2,
            "page_size": 10,
            "sent_after": "2026-06-01T00:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 10
    assert len(body["items"]) == 10
    assert "thread_id" not in response.text
    assert "gmail-msg-" not in response.text


def test_get_paginated_sync_emails_rejects_invalid_paging(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    assert client.get("/sync/emails", params={"page": 0}).status_code == 422
    assert client.get("/sync/emails", params={"page_size": 0}).status_code == 422
    assert client.get("/sync/emails", params={"page_size": 101}).status_code == 422


def test_get_sync_email_content_returns_retained_body(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email_row(
            connection,
            message_id="gmail-msg-1",
            public_id="0123456789abcdef0123456789abcdef",
            sent_at=NOW,
            body_text="Private body",
            body_retention_state="retained",
        )
        insert_email_connection_row(connection)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get("/sync/emails/0123456789abcdef0123456789abcdef/content")

    assert response.status_code == 200
    assert response.json()["body_text"] == "Private body"
    assert "gmail-msg-1" not in response.text


def test_get_sync_email_content_fetches_transient_body_for_metadata_only_message(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email_row(
            connection,
            message_id="gmail-msg-2",
            public_id="00000000000000000000000000000002",
            sent_at=NOW,
        )
        insert_email_connection_row(connection)
    provider = FakeBodyFetchProvider(body_text_by_message_id={"gmail-msg-2": "Fetched text"})
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    client = TestClient(app)

    response = client.get("/sync/emails/00000000000000000000000000000002/content")

    assert response.status_code == 200
    assert response.json()["body_text"] == "Fetched text"
    assert len(provider.fetch_requests) == 1
    with sqlite3.connect(database_path) as connection:
        stored_body = connection.execute(
            "SELECT body_text FROM raw_emails WHERE id = 'gmail-msg-2'"
        ).fetchone()[0]
    assert stored_body is None


def test_get_sync_email_content_returns_404_for_unknown_public_id(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_email_connection_row(connection)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get("/sync/emails/ffffffffffffffffffffffffffffffff/content")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_sync_email_content_returns_404_when_provider_reports_message_missing(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email_row(
            connection,
            message_id="gmail-msg-3",
            public_id="00000000000000000000000000000003",
            sent_at=NOW,
        )
        insert_email_connection_row(connection)
    provider = FakeBodyFetchProvider(
        failure_reason_by_message_id={"gmail-msg-3": EmailBodyFetchFailureReason.NOT_FOUND},
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    client = TestClient(app)

    response = client.get("/sync/emails/00000000000000000000000000000003/content")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_sync_email_content_returns_401_for_reauthentication_required(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email_row(
            connection,
            message_id="gmail-msg-4",
            public_id="00000000000000000000000000000004",
            sent_at=NOW,
        )
        insert_email_connection_row(connection)
    provider = FakeBodyFetchProvider(
        raises_by_message_id={
            "gmail-msg-4": EmailProviderAuthError(public_message="Reauthentication required."),
        },
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    client = TestClient(app)

    response = client.get("/sync/emails/00000000000000000000000000000004/content")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "email_authorization_required"


def test_get_sync_email_content_returns_503_for_transient_provider_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email_row(
            connection,
            message_id="gmail-msg-5",
            public_id="00000000000000000000000000000005",
            sent_at=NOW,
        )
        insert_email_connection_row(connection)
    provider = FakeBodyFetchProvider(
        raises_by_message_id={
            "gmail-msg-5": EmailProviderTransientError(
                public_message="Gmail is temporarily unavailable.",
            ),
        },
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    client = TestClient(app)

    response = client.get("/sync/emails/00000000000000000000000000000005/content")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "email_temporarily_unavailable"


def test_get_sync_email_content_returns_400_when_no_connection_is_configured(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email_row(
            connection,
            message_id="gmail-msg-6",
            public_id="00000000000000000000000000000006",
            sent_at=NOW,
        )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get("/sync/emails/00000000000000000000000000000006/content")

    assert response.status_code == 400


def insert_raw_email_row(
    connection: sqlite3.Connection,
    *,
    message_id: str,
    public_id: str,
    sent_at: datetime,
    body_text: str | None = None,
    body_retention_state: str = "metadata_only",
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id,
            public_id,
            thread_id,
            from_addr,
            to_addr,
            subject,
            sent_at,
            body_text,
            body_retention_state,
            labels,
            provider,
            ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            public_id,
            f"thread-{message_id}",
            "jobs@example.com",
            "me@example.com",
            "Application received",
            sent_at.isoformat(),
            body_text,
            body_retention_state,
            "[]",
            "gmail",
            sent_at.isoformat(),
        ),
    )
    connection.commit()


def insert_email_connection_row(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO email_connections (
            provider,
            account_id,
            display_email,
            credential_ref_kind,
            credential_ref_provider,
            credential_ref_name,
            granted_scopes,
            connected_at,
            reauth_required,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "gmail",
            "me@example.com",
            "me@example.com",
            "oauth_token",
            "gmail",
            "me-example-com",
            json.dumps([GMAIL_READONLY_SCOPE]),
            NOW.isoformat(),
            0,
            NOW.isoformat(),
        ),
    )
    connection.commit()


class FakeBodyFetchProvider:
    def __init__(
        self,
        *,
        body_text_by_message_id: dict[str, str] | None = None,
        failure_reason_by_message_id: dict[str, EmailBodyFetchFailureReason] | None = None,
        raises_by_message_id: dict[str, Exception] | None = None,
    ) -> None:
        self._body_text_by_message_id = body_text_by_message_id or {}
        self._failure_reason_by_message_id = failure_reason_by_message_id or {}
        self._raises_by_message_id = raises_by_message_id or {}
        self.fetch_requests: list[EmailBodyFetchRequest] = []

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        del connection
        self.fetch_requests.append(request)
        ref = request.refs[0]
        if ref.message_id in self._raises_by_message_id:
            raise self._raises_by_message_id[ref.message_id]
        if ref.message_id in self._failure_reason_by_message_id:
            return EmailBodyBatch(
                bodies=(),
                failures=(
                    EmailBodyFetchFailure(
                        ref=ref,
                        reason=self._failure_reason_by_message_id[ref.message_id],
                    ),
                ),
            )
        return EmailBodyBatch(
            bodies=(
                EmailMessageBody(
                    ref=ref,
                    body_text=self._body_text_by_message_id.get(ref.message_id, ""),
                    body_source=EmailBodySource.TEXT_PLAIN,
                    truncated=False,
                    fetched_at=NOW,
                ),
            ),
        )


def email_connection() -> EmailConnection:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailConnection(
        account=account,
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=NOW,
    )


def metadata_message(connection: EmailConnection, message_id: str) -> EmailMessageMetadata:
    return EmailMessageMetadata(
        ref=EmailMessageRef(
            account=connection.account,
            message_id=message_id,
            thread_id=f"thread-{message_id}",
        ),
        from_addr=EmailAddress(address="jobs@example.com"),
        subject="Application received",
        sent_at=NOW,
    )


def create_sync_tables(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE raw_emails (
                id TEXT PRIMARY KEY,
                public_id TEXT,
                thread_id TEXT,
                from_addr TEXT,
                to_addr TEXT,
                subject TEXT,
                sent_at TEXT,
                body_text TEXT,
                body_retention_state TEXT NOT NULL,
                labels TEXT NOT NULL,
                provider TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """,
        )
        connection.execute(
            "CREATE UNIQUE INDEX ux_raw_emails_public_id ON raw_emails(public_id)",
        )
        connection.execute(
            """
            CREATE TABLE email_sync_state (
                provider TEXT NOT NULL,
                account_id TEXT NOT NULL,
                sync_cursor TEXT,
                cursor_issued_at TEXT,
                in_progress_mode TEXT,
                next_page_token TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (provider, account_id)
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE email_filter_decisions (
                email_id TEXT NOT NULL,
                strategy TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                CHECK (strategy IN ('broad_job_search')),
                CHECK (outcome IN ('candidate', 'rejected')),
                PRIMARY KEY (email_id, strategy),
                FOREIGN KEY (email_id) REFERENCES raw_emails(id) ON DELETE CASCADE
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE email_connections (
                provider TEXT NOT NULL,
                account_id TEXT NOT NULL,
                display_email TEXT,
                credential_ref_kind TEXT NOT NULL,
                credential_ref_provider TEXT NOT NULL,
                credential_ref_name TEXT NOT NULL,
                granted_scopes TEXT NOT NULL,
                connected_at TEXT NOT NULL,
                credential_expires_at TEXT,
                reauth_required INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (provider, account_id)
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE email_backfill_state (
                provider TEXT NOT NULL,
                account_id TEXT NOT NULL,
                status TEXT NOT NULL,
                next_page_token TEXT,
                processed_page_count INTEGER NOT NULL DEFAULT 0,
                processed_message_count INTEGER NOT NULL DEFAULT 0,
                sync_cursor TEXT,
                cursor_issued_at TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                last_error TEXT,
                PRIMARY KEY (provider, account_id)
            )
            """,
        )
