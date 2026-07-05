from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from app.config import GMAIL_READONLY_SCOPE, EmailProviderName
from app.db.repositories import EmailRepository
from app.db.repositories.sync_state import SyncStateRepository
from app.pipeline.filter import build_broad_candidate_query
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailBodyBatch,
    EmailBodyFetchRequest,
    EmailBodySource,
    EmailConnection,
    EmailMessageBody,
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
from app.services.sync_service import (
    EmailSyncRunState,
    EmailSyncService,
    EmailSyncStatus,
    SyncScheduler,
    SyncService,
)

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


class RecordingRetainedBodyProvider(RecordingHistoryProvider):
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
        super().__init__()
        self.body_requests: list[EmailBodyFetchRequest] = []

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        self.body_requests.append(request)
        return EmailBodyBatch(
            bodies=tuple(
                EmailMessageBody(
                    ref=ref,
                    body_text=f"Retained body for {ref.message_id}",
                    body_source=EmailBodySource.TEXT_PLAIN,
                    truncated=False,
                    fetched_at=NOW,
                )
                for ref in request.refs
            )
        )


class PagingRetainedBodyProvider(RecordingRetainedBodyProvider):
    def __init__(self, pages: tuple[EmailMetadataPage, ...]) -> None:
        super().__init__()
        self._pages = list(pages)

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        del connection
        self.requests.append(request)
        return self._pages.pop(0)


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


class PagingHistoryProvider:
    def __init__(self, pages: tuple[EmailMetadataPage, ...]) -> None:
        self._pages = list(pages)
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        del connection
        self.requests.append(request)
        return self._pages.pop(0)


class FailingHistoryProvider:
    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        del connection
        self.requests.append(request)
        msg = "provider unavailable"
        raise RuntimeError(msg)


class FailingAfterFirstPageProvider(PagingHistoryProvider):
    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        if self.requests:
            self.requests.append(request)
            msg = "provider unavailable after page one"
            raise RuntimeError(msg)
        return await super().list_message_metadata(connection, request)


class ProgressInspectingProvider(PagingHistoryProvider):
    def __init__(self, pages: tuple[EmailMetadataPage, ...]) -> None:
        super().__init__(pages)
        self.status_reader: Callable[[], EmailSyncStatus | None] = lambda: None

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        if len(self.requests) == 1:
            status = self.status_reader()
            assert status is not None
            assert status.state is EmailSyncRunState.RUNNING
            assert status.page_count == 1
            assert status.message_count == 1
        return await super().list_message_metadata(connection, request)


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


def test_manual_sync_backfills_all_pages_and_persists_latest_cursor() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
    mailbox = email_connection()
    provider = PagingHistoryProvider(
        (
            EmailMetadataPage(
                messages=(metadata_message(mailbox, "gmail-msg-1"),),
                next_page_token="page-2",
                next_sync_cursor=EmailProviderCursor(
                    account=mailbox.account,
                    value="history-page-1",
                    issued_at=NOW,
                ),
            ),
            EmailMetadataPage(
                messages=(metadata_message(mailbox, "gmail-msg-2"),),
                next_sync_cursor=EmailProviderCursor(
                    account=mailbox.account,
                    value="history-page-2",
                    issued_at=NOW,
                ),
            ),
        )
    )
    email_repository = EmailRepository(connection)
    sync_state_repository = SyncStateRepository(connection)
    service = EmailSyncService(
        provider=provider,
        page_size=250,
        email_repository=email_repository,
        sync_service=SyncService(sync_state_repository=sync_state_repository),
        clock=lambda: NOW,
    )

    status = asyncio.run(service.run_manual_sync(connection=mailbox))

    assert status.state is EmailSyncRunState.SUCCEEDED
    assert status.mode is EmailSyncMode.FULL_BACKFILL
    assert status.page_count == 2
    assert status.message_count == 2
    assert status.raw_email_count == 2
    assert status.recovered_from_expired_cursor is False
    assert [request.mode for request in provider.requests] == [
        EmailSyncMode.FULL_BACKFILL,
        EmailSyncMode.FULL_BACKFILL,
    ]
    assert [request.page_token for request in provider.requests] == [None, "page-2"]
    assert email_repository.count_raw_emails(provider=EmailProviderName.GMAIL) == 2
    stored_cursor = sync_state_repository.get_cursor(mailbox.account)
    assert stored_cursor is not None
    assert stored_cursor.value == "history-page-2"


def test_manual_sync_uses_incremental_mode_when_cursor_exists() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
    mailbox = email_connection()
    sync_state_repository = SyncStateRepository(connection)
    sync_state_repository.save_cursor(
        EmailProviderCursor(
            account=mailbox.account,
            value="history-current",
            issued_at=NOW - timedelta(minutes=5),
        ),
        updated_at=NOW - timedelta(minutes=5),
    )
    provider = PagingHistoryProvider(
        (
            EmailMetadataPage(
                messages=(metadata_message(mailbox, "gmail-msg-3"),),
                next_sync_cursor=EmailProviderCursor(
                    account=mailbox.account,
                    value="history-next",
                    issued_at=NOW,
                ),
            ),
        )
    )
    service = EmailSyncService(
        provider=provider,
        page_size=100,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=sync_state_repository),
        clock=lambda: NOW,
    )

    status = asyncio.run(service.run_manual_sync(connection=mailbox))

    assert status.state is EmailSyncRunState.SUCCEEDED
    assert status.mode is EmailSyncMode.INCREMENTAL
    assert len(provider.requests) == 1
    assert provider.requests[0].mode is EmailSyncMode.INCREMENTAL
    assert provider.requests[0].sync_cursor is not None
    assert provider.requests[0].sync_cursor.value == "history-current"
    stored_cursor = sync_state_repository.get_cursor(mailbox.account)
    assert stored_cursor is not None
    assert stored_cursor.value == "history-next"


def test_manual_sync_resumes_failed_full_backfill_from_persisted_page_token() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
    mailbox = email_connection()
    sync_state_repository = SyncStateRepository(connection)
    first_provider = FailingAfterFirstPageProvider(
        (
            EmailMetadataPage(
                messages=(metadata_message(mailbox, "gmail-msg-1"),),
                next_page_token="page-2",
            ),
        )
    )
    service = EmailSyncService(
        provider=first_provider,
        page_size=100,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=sync_state_repository),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="provider unavailable after page one"):
        asyncio.run(service.run_manual_sync(connection=mailbox))

    failed_state = sync_state_repository.fetch_state(mailbox.account)
    assert failed_state is not None
    assert failed_state.in_progress_mode == "full_backfill"
    assert failed_state.next_page_token == "page-2"

    second_provider = PagingHistoryProvider(
        (
            EmailMetadataPage(
                messages=(metadata_message(mailbox, "gmail-msg-2"),),
                next_sync_cursor=EmailProviderCursor(
                    account=mailbox.account,
                    value="history-after-resume",
                    issued_at=NOW,
                ),
            ),
        )
    )
    resumed_service = EmailSyncService(
        provider=second_provider,
        page_size=100,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=sync_state_repository),
        clock=lambda: NOW,
    )

    status = asyncio.run(resumed_service.run_manual_sync(connection=mailbox))

    assert status.state is EmailSyncRunState.SUCCEEDED
    assert status.mode is EmailSyncMode.FULL_BACKFILL
    assert status.raw_email_count == 2
    assert len(second_provider.requests) == 1
    assert second_provider.requests[0].mode is EmailSyncMode.FULL_BACKFILL
    assert second_provider.requests[0].page_token == "page-2"
    stored_state = sync_state_repository.fetch_state(mailbox.account)
    assert stored_state is not None
    assert stored_state.sync_cursor == "history-after-resume"
    assert stored_state.in_progress_mode is None
    assert stored_state.next_page_token is None


def test_manual_sync_metadata_upsert_preserves_existing_retained_body() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
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
        ) VALUES (
            'gmail-msg-1',
            'thread-old',
            'jobs@example.com',
            'me@example.com',
            'Old subject',
            ?,
            'Retained candidate body',
            'retained',
            '[]',
            'gmail',
            ?
        )
        """,
        (NOW.isoformat(), NOW.isoformat()),
    )
    mailbox = email_connection()
    provider = PagingHistoryProvider(
        (EmailMetadataPage(messages=(metadata_message(mailbox, "gmail-msg-1"),)),)
    )
    service = EmailSyncService(
        provider=provider,
        page_size=250,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=SyncStateRepository(connection)),
        clock=lambda: NOW,
    )

    asyncio.run(service.run_manual_sync(connection=mailbox))

    row = connection.execute(
        "SELECT body_text, body_retention_state, subject FROM raw_emails WHERE id = ?",
        ("gmail-msg-1",),
    ).fetchone()
    assert row is not None
    assert tuple(row) == ("Retained candidate body", "retained", "Application received")


def test_manual_sync_persists_retained_bodies_for_candidate_messages() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
    mailbox = email_connection()
    provider = PagingRetainedBodyProvider(
        (
            EmailMetadataPage(
                messages=(
                    EmailMessageMetadata(
                        ref=EmailMessageRef(
                            account=mailbox.account,
                            message_id="gmail-candidate",
                            thread_id="thread-candidate",
                        ),
                        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
                        to_addrs=(EmailAddress(address="me@example.com"),),
                        subject="Application received",
                        sent_at=NOW,
                        labels=("INBOX",),
                    ),
                    EmailMessageMetadata(
                        ref=EmailMessageRef(
                            account=mailbox.account,
                            message_id="gmail-newsletter",
                            thread_id="thread-newsletter",
                        ),
                        from_addr=EmailAddress(address="news@example.com"),
                        to_addrs=(EmailAddress(address="me@example.com"),),
                        subject="Product newsletter",
                        sent_at=NOW,
                        labels=("INBOX",),
                    ),
                ),
                next_sync_cursor=EmailProviderCursor(
                    account=mailbox.account,
                    value="history-next",
                    issued_at=NOW,
                ),
            ),
        )
    )
    service = EmailSyncService(
        provider=provider,
        page_size=250,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=SyncStateRepository(connection)),
        clock=lambda: NOW,
    )

    asyncio.run(service.run_manual_sync(connection=mailbox))

    rows = connection.execute(
        "SELECT id, body_text, body_retention_state FROM raw_emails ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("gmail-candidate", "Retained body for gmail-candidate", "retained"),
        ("gmail-newsletter", None, "metadata_only"),
    ]
    assert len(provider.body_requests) == 1
    assert [ref.message_id for ref in provider.body_requests[0].refs] == ["gmail-candidate"]


def test_manual_sync_updates_running_status_between_pages() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
    mailbox = email_connection()
    provider = ProgressInspectingProvider(
        (
            EmailMetadataPage(
                messages=(metadata_message(mailbox, "gmail-msg-1"),),
                next_page_token="page-2",
            ),
            EmailMetadataPage(messages=(metadata_message(mailbox, "gmail-msg-2"),)),
        )
    )
    service = EmailSyncService(
        provider=provider,
        page_size=250,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=SyncStateRepository(connection)),
        clock=lambda: NOW,
    )
    provider.status_reader = service.current_status

    asyncio.run(service.run_manual_sync(connection=mailbox))

    assert service.current_status().state is EmailSyncRunState.SUCCEEDED


def test_manual_sync_records_failed_status_when_provider_fails() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    create_email_sync_state_table(connection)
    provider = FailingHistoryProvider()
    service = EmailSyncService(
        provider=provider,
        page_size=100,
        email_repository=EmailRepository(connection),
        sync_service=SyncService(sync_state_repository=SyncStateRepository(connection)),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(service.run_manual_sync(connection=email_connection()))

    status = service.current_status()
    assert status.state is EmailSyncRunState.FAILED
    assert status.last_error == "Sync failed."
    assert status.finished_at == NOW


def test_sync_service_fetches_retained_bodies_only_for_candidates_and_debug_refs() -> None:
    provider = RecordingRetainedBodyProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    candidate = EmailMessageMetadata(
        ref=EmailMessageRef(
            account=connection.account,
            message_id="msg-candidate",
            thread_id="thread-candidate",
        ),
        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
        subject="Weekly digest",
        labels=("INBOX",),
    )
    non_candidate = EmailMessageMetadata(
        ref=EmailMessageRef(
            account=connection.account,
            message_id="msg-newsletter",
            thread_id="thread-newsletter",
        ),
        from_addr=EmailAddress(address="news@example.com"),
        subject="Product newsletter",
        labels=("INBOX",),
    )
    debugging_ref = EmailMessageRef(
        account=connection.account,
        message_id="msg-debugging",
        thread_id="thread-debugging",
    )

    batch = asyncio.run(
        service.fetch_retained_bodies(
            connection=connection,
            metadata=(candidate, non_candidate),
            candidate_query=build_broad_candidate_query(),
            reconciliation_or_debug_refs=(debugging_ref,),
            max_body_bytes=10_000,
        )
    )

    assert [body.ref.message_id for body in batch.bodies] == [
        "msg-candidate",
        "msg-debugging",
    ]
    assert len(provider.body_requests) == 1
    assert [ref.message_id for ref in provider.body_requests[0].refs] == [
        "msg-candidate",
        "msg-debugging",
    ]
    assert provider.body_requests[0].max_body_bytes == 10_000


def test_sync_service_chunks_retained_body_fetches_by_provider_limit() -> None:
    provider = RecordingRetainedBodyProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    metadata = tuple(
        EmailMessageMetadata(
            ref=EmailMessageRef(
                account=connection.account,
                message_id=f"msg-candidate-{index}",
                thread_id=f"thread-candidate-{index}",
            ),
            from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
            subject="Application received",
            labels=("INBOX",),
        )
        for index in range(101)
    )

    batch = asyncio.run(
        service.fetch_retained_bodies(
            connection=connection,
            metadata=metadata,
            candidate_query=build_broad_candidate_query(),
            max_body_bytes=10_000,
        )
    )

    assert len(batch.bodies) == 101
    assert [len(request.refs) for request in provider.body_requests] == [100, 1]
    assert provider.body_requests[0].refs[0].message_id == "msg-candidate-0"
    assert provider.body_requests[1].refs[0].message_id == "msg-candidate-100"
    assert all(request.max_body_bytes == 10_000 for request in provider.body_requests)


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


def metadata_message(connection: EmailConnection, message_id: str) -> EmailMessageMetadata:
    return EmailMessageMetadata(
        ref=EmailMessageRef(
            account=connection.account,
            message_id=message_id,
            thread_id=f"thread-{message_id}",
        ),
        from_addr=EmailAddress(address="jobs@example.com"),
        to_addrs=(EmailAddress(address="me@example.com"),),
        subject="Application received",
        sent_at=NOW,
        labels=("INBOX",),
    )


def create_raw_emails_table(connection: sqlite3.Connection) -> None:
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


def create_email_sync_state_table(connection: sqlite3.Connection) -> None:
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
