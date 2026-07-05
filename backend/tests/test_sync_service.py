from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from app.config import GMAIL_READONLY_SCOPE, EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailConnection,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCapabilities,
    EmailProviderCursor,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef
from app.services.sync_service import EmailSyncService, SyncScheduler

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class ExpiringHistoryProvider:
    name = EmailProviderName.GMAIL
    capabilities = EmailProviderCapabilities(
        provider=EmailProviderName.GMAIL,
        required_scopes=(GMAIL_READONLY_SCOPE,),
        supports_oauth=True,
        supports_full_backfill=True,
        supports_incremental_sync=True,
        attachment_policy=EmailAttachmentPolicy.IGNORED,
        max_metadata_page_size=500,
        max_body_batch_size=100,
    )

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
            messages=(
                EmailMessageMetadata(
                    ref=EmailMessageRef(
                        account=connection.account,
                        message_id="msg-reconciled",
                        thread_id="thread-reconciled",
                    ),
                    from_addr=EmailAddress(address="jobs@example.com"),
                    subject="Application received",
                    received_at=NOW,
                ),
            ),
            next_page_token="page-2",
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-recovered",
                issued_at=NOW,
            ),
        )


class RecordingHistoryProvider:
    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        return EmailMetadataPage(
            messages=(),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-next",
                issued_at=NOW,
            ),
        )


class RecordingScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict[str, object]] = []
        self.started = False
        self.shutdown_wait: bool | None = None

    def add_job(
        self,
        func: object,
        trigger: str,
        *,
        seconds: int,
        id: str,
        replace_existing: bool,
        next_run_time: datetime | None,
    ) -> None:
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "seconds": seconds,
                "id": id,
                "replace_existing": replace_existing,
                "next_run_time": next_run_time,
            }
        )

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, wait: bool) -> None:
        self.shutdown_wait = wait


def test_expired_history_id_falls_back_to_resumable_reconciliation() -> None:
    provider = ExpiringHistoryProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    expired_cursor = EmailProviderCursor(
        account=connection.account,
        value="history-expired",
        issued_at=NOW - timedelta(days=30),
    )

    result = asyncio.run(
        service.list_metadata_page(
            connection=connection,
            sync_cursor=expired_cursor,
        )
    )

    assert result.recovered_from_expired_cursor is True
    assert result.mode is EmailSyncMode.FULL_BACKFILL
    assert result.page.next_page_token == "page-2"
    assert result.page.next_sync_cursor is not None
    assert result.page.next_sync_cursor.value == "history-recovered"
    assert [request.mode for request in provider.requests] == [
        EmailSyncMode.INCREMENTAL,
        EmailSyncMode.FULL_BACKFILL,
    ]
    assert provider.requests[0].sync_cursor == expired_cursor
    assert provider.requests[1].sync_cursor is None
    assert provider.requests[1].page_size == 250


def test_sync_scheduler_starts_immediate_interval_job_when_enabled() -> None:
    scheduler_backend = RecordingScheduler()
    calls = 0

    async def sync_job() -> None:
        nonlocal calls
        calls += 1

    scheduler = SyncScheduler(
        sync_on_open=True,
        interval_seconds=300,
        sync_job=sync_job,
        scheduler=scheduler_backend,
    )

    scheduler.start()

    assert scheduler_backend.started is True
    assert len(scheduler_backend.jobs) == 1
    job = scheduler_backend.jobs[0]
    assert job["trigger"] == "interval"
    assert job["seconds"] == 300
    assert job["id"] == "gmail-sync-on-open"
    assert job["replace_existing"] is True
    assert isinstance(job["next_run_time"], datetime)
    job_func = job["func"]
    assert callable(job_func)
    asyncio.run(job_func())
    assert calls == 1


def test_sync_scheduler_does_not_start_when_sync_on_open_disabled() -> None:
    scheduler_backend = RecordingScheduler()

    async def sync_job() -> None:
        raise AssertionError("disabled scheduler must not run sync")

    scheduler = SyncScheduler(
        sync_on_open=False,
        interval_seconds=300,
        sync_job=sync_job,
        scheduler=scheduler_backend,
    )

    scheduler.start()
    scheduler.shutdown()

    assert scheduler_backend.started is False
    assert scheduler_backend.jobs == []
    assert scheduler_backend.shutdown_wait is None


def test_sync_scheduler_shutdown_stops_started_scheduler_without_waiting() -> None:
    scheduler_backend = RecordingScheduler()

    async def sync_job() -> None:
        return None

    scheduler = SyncScheduler(
        sync_on_open=True,
        interval_seconds=300,
        sync_job=sync_job,
        scheduler=scheduler_backend,
    )

    scheduler.start()
    scheduler.shutdown()

    assert scheduler_backend.shutdown_wait is False


def test_incremental_metadata_page_forwards_resume_page_token() -> None:
    provider = RecordingHistoryProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    cursor = EmailProviderCursor(
        account=connection.account,
        value="history-current",
        issued_at=NOW,
    )

    result = asyncio.run(
        service.list_metadata_page(
            connection=connection,
            mode=EmailSyncMode.INCREMENTAL,
            sync_cursor=cursor,
            page_token="incremental-page-2",
        )
    )

    assert result.recovered_from_expired_cursor is False
    assert result.mode is EmailSyncMode.INCREMENTAL
    assert len(provider.requests) == 1
    assert provider.requests[0].mode is EmailSyncMode.INCREMENTAL
    assert provider.requests[0].sync_cursor == cursor
    assert provider.requests[0].page_token == "incremental-page-2"


def test_reconciliation_continuation_uses_full_backfill_mode_with_cursor_present() -> None:
    provider = RecordingHistoryProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    cursor = EmailProviderCursor(
        account=connection.account,
        value="history-recovered",
        issued_at=NOW,
    )

    result = asyncio.run(
        service.list_metadata_page(
            connection=connection,
            mode=EmailSyncMode.FULL_BACKFILL,
            sync_cursor=cursor,
            page_token="reconciliation-page-2",
        )
    )

    assert result.mode is EmailSyncMode.FULL_BACKFILL
    assert len(provider.requests) == 1
    assert provider.requests[0].mode is EmailSyncMode.FULL_BACKFILL
    assert provider.requests[0].sync_cursor is None
    assert provider.requests[0].page_token == "reconciliation-page-2"


def test_paginated_sync_with_cursor_requires_explicit_mode() -> None:
    provider = RecordingHistoryProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    cursor = EmailProviderCursor(
        account=connection.account,
        value="history-current",
        issued_at=NOW,
    )

    with pytest.raises(ValueError, match="mode is required"):
        asyncio.run(
            service.list_metadata_page(
                connection=connection,
                sync_cursor=cursor,
                page_token="ambiguous-page-2",
            )
        )

    assert provider.requests == []


def email_connection() -> EmailConnection:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailConnection(
        account=account,
        display_email=EmailAddress(address="me@example.com"),
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=NOW,
    )
