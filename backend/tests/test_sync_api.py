from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
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
    EmailConnection,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProvider,
    EmailProviderAuthError,
    EmailProviderCursor,
    EmailProviderErrorCode,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gmail-msg-1",
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
            "from_domain": "example.com",
            "to_domains": ["example.com"],
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
        for email_id, sent_at, ingested_at in rows:
            connection.execute(
                """
                INSERT INTO raw_emails (
                    id, thread_id, from_addr, to_addr, subject, sent_at,
                    body_text, body_retention_state, labels, provider, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'metadata_only', '[]', 'gmail', ?)
                """,
                (
                    email_id,
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
