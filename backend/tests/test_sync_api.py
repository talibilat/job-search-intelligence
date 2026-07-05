from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from app.api.sync import (
    ConfiguredEmailSyncRuntime,
    EmailSyncStatusStore,
    get_email_sync_connection,
    get_email_sync_runtime,
    get_sync_email_provider,
    get_sync_status_store,
)
from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName, get_settings
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
    EmailProviderErrorCode,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef
from app.services.sync_service import (
    EmailSyncRunState,
    EmailSyncStatus,
    SyncAlreadyRunningError,
)
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class FakeSyncRuntime:
    def __init__(self) -> None:
        self.run_count = 0
        self.status = EmailSyncStatus(state=EmailSyncRunState.IDLE)

    async def run_manual_sync(self) -> EmailSyncStatus:
        self.run_count += 1
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
            recovered_from_expired_cursor=False,
        )
        return self.status

    def current_status(self) -> EmailSyncStatus:
        return self.status


class ProviderErrorSyncRuntime:
    async def run_manual_sync(self) -> EmailSyncStatus:
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
            )
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
        return EmailMetadataPage(messages=(metadata_message(connection, "gmail-msg-1"),))


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
        "recovered_from_expired_cursor": False,
        "last_error": None,
    }


def test_get_sync_status_returns_current_runtime_status() -> None:
    runtime = FakeSyncRuntime()
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json()["state"] == "idle"


def test_post_sync_returns_typed_error_until_gmail_connection_is_configured() -> None:
    client = TestClient(create_app())

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


def test_post_sync_uses_dependency_wired_provider_repositories_and_connection(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_sync_tables(database_path)
    provider = FakeMetadataProvider()
    status_store = EmailSyncStatusStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        gmail_page_size=77,
    )
    app.dependency_overrides[get_sync_email_provider] = lambda: provider
    app.dependency_overrides[get_email_sync_connection] = email_connection
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
    assert row == (1,)


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
            connection=email_connection(),
            status_store=EmailSyncStatusStore(),
        )

        first_run = asyncio.create_task(runtime.run_manual_sync())
        await provider.started.wait()

        with pytest.raises(SyncAlreadyRunningError):
            await asyncio.wait_for(runtime.run_manual_sync(), timeout=0.1)

        provider.release.set()
        await first_run

    asyncio.run(run_test())


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
