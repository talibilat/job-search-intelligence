from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from app.config import EmailProviderName
from app.db.repositories import (
    BackfillStateRepository,
    EmailFilterDecisionRepository,
    EmailRepository,
)
from app.db.repositories.sync_state import SyncStateRepository
from app.models import SyncJobCounts, SyncJobPhase, SyncJobStatus
from app.models.records import (
    EmailBackfillStateRecord,
    EmailBackfillStatus,
    EmailFilterDecisionRecord,
    EmailSyncStateRecord,
    RawEmailBodyRetentionState,
)
from app.providers.email import (
    EmailAccountRef,
    EmailBodyBatch,
    EmailBodyFetchFailure,
    EmailBodyFetchRequest,
    EmailCandidateQuery,
    EmailConnection,
    EmailMessageBody,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCapabilities,
    EmailProviderCursor,
    EmailProviderError,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
    build_broad_candidate_query,
)

SyncJob = Callable[[], Awaitable[None]]
SYNC_ON_OPEN_JOB_ID = "gmail-sync-on-open"


class ScheduledJobScheduler(Protocol):
    def add_job(
        self,
        func: Callable[[], Awaitable[None]],
        trigger: str,
        *,
        seconds: int,
        id: str,
        replace_existing: bool,
        next_run_time: datetime | None,
    ) -> object:
        """Schedule one async job."""
        ...

    def start(self) -> None:
        """Start executing scheduled jobs."""
        ...

    def shutdown(self, *, wait: bool) -> None:
        """Stop executing scheduled jobs."""
        ...


def create_apscheduler() -> ScheduledJobScheduler:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

    return cast(ScheduledJobScheduler, AsyncIOScheduler())


async def noop_sync_job() -> None:
    """Safe placeholder until the concrete Gmail sync runner is wired in."""


class SyncScheduler:
    """Own APScheduler lifetime for sync jobs while the backend process runs."""

    def __init__(
        self,
        *,
        sync_on_open: bool,
        interval_seconds: int,
        sync_job: SyncJob,
        scheduler: ScheduledJobScheduler | None = None,
    ) -> None:
        if interval_seconds < 1:
            msg = "interval_seconds must be at least 1"
            raise ValueError(msg)

        self._sync_on_open = sync_on_open
        self._interval_seconds = interval_seconds
        self._sync_job = sync_job
        self._scheduler = scheduler or create_apscheduler()
        self._started = False

    def start(self) -> None:
        if not self._sync_on_open or self._started:
            return

        self._scheduler.add_job(
            self._sync_job,
            "interval",
            seconds=self._interval_seconds,
            id=SYNC_ON_OPEN_JOB_ID,
            replace_existing=True,
            next_run_time=datetime.now(UTC),
        )
        self._scheduler.start()
        self._started = True

    def shutdown(self) -> None:
        if not self._started:
            return

        self._scheduler.shutdown(wait=False)
        self._started = False


class EmailSyncRunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EmailSyncStatus(BaseModel):
    """Current or last manual sync run status exposed at the API boundary."""

    provider: EmailProviderName | None = None
    account_id: str | None = None
    state: EmailSyncRunState
    mode: EmailSyncMode | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    page_count: int = Field(default=0, ge=0)
    message_count: int = Field(default=0, ge=0)
    raw_email_count: int = Field(default=0, ge=0)
    recovered_from_expired_cursor: bool = False
    last_error: str | None = None


class SyncAlreadyRunningError(RuntimeError):
    """Raised when a manual sync starts while another run is active."""


class SyncConnectionNotConfiguredError(RuntimeError):
    """Raised when a sync run has no configured account connection."""


class EmailSyncRuntime(Protocol):
    async def run_manual_sync(self) -> EmailSyncStatus:
        """Run a manual sync for the configured account."""
        ...

    def current_status(self) -> EmailSyncStatus:
        """Return current or last-run status."""
        ...


class SyncService:
    """Business seam for email sync state used by full and incremental runs."""

    def __init__(self, *, sync_state_repository: SyncStateRepository) -> None:
        self._sync_state_repository = sync_state_repository

    def get_sync_cursor(self, account: EmailAccountRef) -> EmailProviderCursor | None:
        return self._sync_state_repository.get_cursor(account)

    def get_sync_state(self, account: EmailAccountRef) -> EmailSyncStateRecord | None:
        return self._sync_state_repository.fetch_state(account)

    def get_sync_status(self, account: EmailAccountRef) -> EmailSyncStateStatus | None:
        state = self._sync_state_repository.fetch_state(account)
        if state is None:
            return None

        cursor = None
        if state.sync_cursor is not None and state.cursor_issued_at is not None:
            cursor = EmailProviderCursor(
                account=EmailAccountRef(
                    provider=EmailProviderName(state.provider),
                    account_id=state.account_id,
                ),
                value=state.sync_cursor,
                issued_at=state.cursor_issued_at,
            )

        return EmailSyncStateStatus(
            account=EmailAccountRef(
                provider=EmailProviderName(state.provider),
                account_id=state.account_id,
            ),
            cursor=cursor,
            last_state_update_at=state.updated_at,
        )

    def store_sync_cursor(
        self,
        cursor: EmailProviderCursor,
        *,
        updated_at: datetime | None = None,
    ) -> EmailSyncStateRecord:
        return self._sync_state_repository.save_cursor(
            cursor,
            updated_at=updated_at or datetime.now(UTC),
        )

    def store_page_progress(
        self,
        account: EmailAccountRef,
        *,
        mode: EmailSyncMode,
        next_page_token: str,
        sync_cursor: EmailProviderCursor | None,
        updated_at: datetime | None = None,
    ) -> EmailSyncStateRecord:
        return self._sync_state_repository.save_page_progress(
            account,
            mode=mode,
            next_page_token=next_page_token,
            sync_cursor=sync_cursor,
            updated_at=updated_at or datetime.now(UTC),
        )

    def clear_page_progress(
        self,
        account: EmailAccountRef,
        *,
        updated_at: datetime | None = None,
    ) -> EmailSyncStateRecord | None:
        return self._sync_state_repository.clear_page_progress(
            account,
            updated_at=updated_at or datetime.now(UTC),
        )


class EmailSyncStateStatus(BaseModel):
    """Persisted sync cursor snapshot for service-level status checks."""

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    cursor: EmailProviderCursor | None
    last_state_update_at: datetime


class BackfillStateService:
    """Business seam for durable full-backfill progress and resumability."""

    def __init__(
        self,
        *,
        backfill_state_repository: BackfillStateRepository,
        sync_state_repository: SyncStateRepository,
    ) -> None:
        if backfill_state_repository.connection is not sync_state_repository.connection:
            msg = "backfill and sync state repositories must share one connection"
            raise ValueError(msg)
        self._backfill_state_repository = backfill_state_repository
        self._sync_state_repository = sync_state_repository

    def get_backfill_state(self, account: EmailAccountRef) -> EmailBackfillStateRecord | None:
        return self._backfill_state_repository.fetch_state(account)

    def start_or_resume_backfill(
        self,
        account: EmailAccountRef,
        *,
        started_at: datetime,
    ) -> EmailBackfillStateRecord:
        existing = self._backfill_state_repository.fetch_state(account)
        if existing is not None and existing.status is not EmailBackfillStatus.COMPLETED:
            return self._backfill_state_repository.save_state(
                existing.model_copy(
                    update={
                        "status": EmailBackfillStatus.RUNNING,
                        "updated_at": started_at,
                        "completed_at": None,
                        "last_error": None,
                    }
                )
            )

        return self._backfill_state_repository.save_state(
            EmailBackfillStateRecord(
                provider=account.provider.value,
                account_id=account.account_id,
                status=EmailBackfillStatus.RUNNING,
                next_page_token=None,
                processed_page_count=0,
                processed_message_count=0,
                sync_cursor=None,
                cursor_issued_at=None,
                started_at=started_at,
                updated_at=started_at,
                completed_at=None,
                last_error=None,
            )
        )

    def record_backfill_page(
        self,
        account: EmailAccountRef,
        *,
        page: EmailMetadataPage,
        expected_page_token: str | None = None,
        updated_at: datetime,
    ) -> EmailBackfillStateRecord:
        existing = self._backfill_state_repository.fetch_state(account)
        if existing is None:
            existing = self.start_or_resume_backfill(account, started_at=updated_at)

        if existing.status is EmailBackfillStatus.COMPLETED:
            msg = "completed backfill pages cannot be recorded again"
            raise ValueError(msg)

        if expected_page_token != existing.next_page_token:
            msg = "recorded backfill page does not match current resume token"
            raise ValueError(msg)

        is_final_page = page.next_page_token is None
        if is_final_page and page.next_sync_cursor is None:
            msg = "completed backfills require a replacement sync cursor"
            raise ValueError(msg)

        if page.next_sync_cursor is not None and page.next_sync_cursor.account != account:
            msg = "replacement sync cursor must belong to the same account"
            raise ValueError(msg)

        sync_cursor = page.next_sync_cursor.value if page.next_sync_cursor is not None else None
        cursor_issued_at = (
            page.next_sync_cursor.issued_at if page.next_sync_cursor is not None else None
        )

        status = (
            EmailBackfillStatus.RUNNING
            if page.next_page_token is not None
            else EmailBackfillStatus.COMPLETED
        )

        connection = self._backfill_state_repository.connection
        should_commit = not connection.in_transaction
        with self._backfill_state_repository.transaction():
            record = self._backfill_state_repository.save_state(
                EmailBackfillStateRecord(
                    provider=account.provider.value,
                    account_id=account.account_id,
                    status=status,
                    next_page_token=page.next_page_token,
                    processed_page_count=existing.processed_page_count + 1,
                    processed_message_count=existing.processed_message_count + len(page.messages),
                    sync_cursor=sync_cursor,
                    cursor_issued_at=cursor_issued_at,
                    started_at=existing.started_at,
                    updated_at=updated_at,
                    completed_at=updated_at if status is EmailBackfillStatus.COMPLETED else None,
                    last_error=None,
                )
            )
            if page.next_sync_cursor is not None and status is EmailBackfillStatus.COMPLETED:
                self._sync_state_repository.save_cursor(
                    page.next_sync_cursor,
                    updated_at=updated_at,
                )

        if should_commit:
            connection.commit()

        return record

    def mark_backfill_failed(
        self,
        account: EmailAccountRef,
        *,
        public_error: str,
        updated_at: datetime,
    ) -> EmailBackfillStateRecord:
        existing = self._backfill_state_repository.fetch_state(account)
        if existing is None:
            existing = self.start_or_resume_backfill(account, started_at=updated_at)

        return self._backfill_state_repository.save_state(
            existing.model_copy(
                update={
                    "status": EmailBackfillStatus.FAILED,
                    "updated_at": updated_at,
                    "completed_at": None,
                    "last_error": public_error,
                }
            )
        )


class MetadataListingProvider(Protocol):
    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        """Return one provider-normalized metadata page."""
        ...


class RetainedBodyProvider(Protocol):
    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        """Return retained bodies for selected provider message refs."""
        ...


class EmailSyncPageResult(BaseModel):
    """One metadata sync page plus the mode that produced it."""

    model_config = ConfigDict(frozen=True)

    mode: EmailSyncMode
    page: EmailMetadataPage
    recovered_from_expired_cursor: bool = False


class EmailBackfillPageResult(BaseModel):
    """One full-backfill page plus the durable state used to select its resume token."""

    model_config = ConfigDict(frozen=True)

    mode: EmailSyncMode = EmailSyncMode.FULL_BACKFILL
    page: EmailMetadataPage
    state: EmailBackfillStateRecord


class EmailSyncService:
    """Service-layer coordination for resumable sync and retained-body storage."""

    def __init__(
        self,
        *,
        provider: MetadataListingProvider,
        page_size: int,
        email_repository: EmailRepository | None = None,
        sync_service: SyncService | None = None,
        clock: Callable[[], datetime] | None = None,
        status_callback: Callable[[EmailSyncStatus], None] | None = None,
        body_provider: RetainedBodyProvider | None = None,
        filter_decision_repository: EmailFilterDecisionRepository | None = None,
    ) -> None:
        if page_size < 1:
            msg = "page_size must be at least 1"
            raise ValueError(msg)
        self._provider = provider
        self._body_provider = body_provider or cast(RetainedBodyProvider, provider)
        self._page_size = page_size
        self._email_repository = email_repository
        self._sync_service = sync_service
        self._clock = clock or _utcnow
        self._status_callback = status_callback
        self._filter_decision_repository = filter_decision_repository
        self._status = EmailSyncStatus(state=EmailSyncRunState.IDLE)

    def current_status(self) -> EmailSyncStatus:
        return self._status

    async def run_manual_sync(self, *, connection: EmailConnection) -> EmailSyncStatus:
        """Run metadata sync and retain bodies for broad job-search candidates."""

        if self._email_repository is None or self._sync_service is None:
            raise SyncConnectionNotConfiguredError("Sync repositories are not configured.")
        if self._status.state is EmailSyncRunState.RUNNING:
            raise SyncAlreadyRunningError("Email sync is already running.")

        started_at = self._clock()
        sync_state = self._sync_service.get_sync_state(connection.account)
        existing_cursor = self._sync_service.get_sync_cursor(connection.account)
        resume_page_token = sync_state.next_page_token if sync_state is not None else None
        resume_mode = (
            EmailSyncMode(sync_state.in_progress_mode)
            if sync_state is not None
            and sync_state.in_progress_mode is not None
            and sync_state.next_page_token is not None
            else None
        )
        requested_mode = resume_mode or (
            EmailSyncMode.INCREMENTAL
            if existing_cursor is not None
            else EmailSyncMode.FULL_BACKFILL
        )
        self._set_status(
            EmailSyncStatus(
                provider=connection.account.provider,
                account_id=connection.account.account_id,
                state=EmailSyncRunState.RUNNING,
                mode=requested_mode,
                started_at=started_at,
            )
        )

        try:
            result = await self._run_metadata_pages(
                connection=connection,
                sync_cursor=existing_cursor,
                initial_mode=resume_mode,
                initial_page_token=resume_page_token,
                started_at=started_at,
            )
        except Exception as error:
            self._set_status(
                self._status.model_copy(
                    update={
                        "state": EmailSyncRunState.FAILED,
                        "finished_at": self._clock(),
                        "last_error": _public_sync_error_message(error),
                    }
                )
            )
            raise

        self._set_status(result)
        return result

    def _set_status(self, status: EmailSyncStatus) -> None:
        self._status = status
        if self._status_callback is not None:
            self._status_callback(status)

    async def list_metadata_page(
        self,
        *,
        connection: EmailConnection,
        mode: EmailSyncMode | None = None,
        sync_cursor: EmailProviderCursor | None = None,
        page_token: str | None = None,
    ) -> EmailSyncPageResult:
        """List one metadata page, falling back when an incremental cursor expires.

        A stale Gmail history ID invalidates incremental sync. When the provider
        reports that state, restart as a full metadata reconciliation page. The
        returned provider page keeps its `next_page_token` and `next_sync_cursor`
        so the caller can persist progress and continue the reconciliation.
        """

        if page_token is not None and sync_cursor is not None and mode is None:
            msg = "mode is required when continuing paginated sync with a cursor"
            raise ValueError(msg)

        sync_mode = mode or (
            EmailSyncMode.INCREMENTAL if sync_cursor is not None else EmailSyncMode.FULL_BACKFILL
        )

        if sync_mode is EmailSyncMode.FULL_BACKFILL:
            page = await self._list_full_backfill_page(connection, page_token=page_token)
            return EmailSyncPageResult(mode=EmailSyncMode.FULL_BACKFILL, page=page)

        if sync_cursor is None:
            msg = "sync_cursor is required for incremental metadata sync"
            raise ValueError(msg)

        try:
            page = await self._provider.list_message_metadata(
                connection,
                EmailMetadataListRequest(
                    mode=EmailSyncMode.INCREMENTAL,
                    page_size=self._page_size,
                    page_token=page_token,
                    sync_cursor=sync_cursor,
                ),
            )
        except EmailSyncCursorExpiredError:
            page = await self._list_full_backfill_page(connection, page_token=None)
            return EmailSyncPageResult(
                mode=EmailSyncMode.FULL_BACKFILL,
                page=page,
                recovered_from_expired_cursor=True,
            )

        return EmailSyncPageResult(mode=EmailSyncMode.INCREMENTAL, page=page)

    async def run_backfill_page(
        self,
        *,
        connection: EmailConnection,
        backfill_state_service: BackfillStateService,
        updated_at: datetime | None = None,
    ) -> EmailBackfillPageResult:
        """List one page; callers persist raw emails before recording page progress."""

        timestamp = updated_at or datetime.now(UTC)
        state = backfill_state_service.start_or_resume_backfill(
            connection.account,
            started_at=timestamp,
        )

        try:
            page = await self._list_full_backfill_page(
                connection,
                page_token=state.next_page_token,
            )
        except EmailProviderError as error:
            backfill_state_service.mark_backfill_failed(
                connection.account,
                public_error=error.public_message,
                updated_at=timestamp,
            )
            raise

        return EmailBackfillPageResult(
            page=page,
            state=state,
        )

    async def run_full_backfill(
        self,
        *,
        connection: EmailConnection,
        backfill_state_service: BackfillStateService,
    ) -> EmailSyncStatus:
        """Run a resumable full metadata backfill and retain candidate bodies."""

        if self._email_repository is None:
            raise SyncConnectionNotConfiguredError("Sync repositories are not configured.")
        if self._status.state is EmailSyncRunState.RUNNING:
            raise SyncAlreadyRunningError("Email sync is already running.")

        started_at = self._clock()
        self._set_status(
            EmailSyncStatus(
                provider=connection.account.provider,
                account_id=connection.account.account_id,
                state=EmailSyncRunState.RUNNING,
                mode=EmailSyncMode.FULL_BACKFILL,
                started_at=started_at,
            )
        )

        page_count = 0
        message_count = 0
        try:
            while True:
                page_result = await self.run_backfill_page(
                    connection=connection,
                    backfill_state_service=backfill_state_service,
                    updated_at=self._clock(),
                )
                page = page_result.page
                if page.messages:
                    self._email_repository.upsert_metadata_only(
                        page.messages,
                        ingested_at=self._clock(),
                    )
                    self._persist_filter_decisions(
                        page.messages,
                        candidate_query=build_broad_candidate_query(),
                    )
                    if _can_fetch_retained_bodies(self._body_provider):
                        body_batch = await self.fetch_retained_bodies(
                            connection=connection,
                            metadata=page.messages,
                            candidate_query=build_broad_candidate_query(),
                        )
                        _raise_for_retained_body_failures(body_batch)
                        if body_batch.bodies:
                            self._email_repository.upsert_retained_bodies(
                                body_batch.bodies,
                                retention_state=RawEmailBodyRetentionState.RETAINED,
                            )

                state = backfill_state_service.record_backfill_page(
                    connection.account,
                    page=page,
                    expected_page_token=page_result.state.next_page_token,
                    updated_at=self._clock(),
                )
                page_count = state.processed_page_count
                message_count = state.processed_message_count
                self._set_status(
                    EmailSyncStatus(
                        provider=connection.account.provider,
                        account_id=connection.account.account_id,
                        state=EmailSyncRunState.RUNNING,
                        mode=EmailSyncMode.FULL_BACKFILL,
                        started_at=started_at,
                        page_count=page_count,
                        message_count=message_count,
                        raw_email_count=self._email_repository.count_raw_emails(
                            provider=connection.account.provider,
                        ),
                    )
                )
                if state.status is EmailBackfillStatus.COMPLETED:
                    break
        except Exception as error:
            public_error = _public_sync_error_message(error)
            backfill_state_service.mark_backfill_failed(
                connection.account,
                public_error=public_error,
                updated_at=self._clock(),
            )
            self._set_status(
                self._status.model_copy(
                    update={
                        "state": EmailSyncRunState.FAILED,
                        "finished_at": self._clock(),
                        "last_error": public_error,
                    }
                )
            )
            raise

        status = EmailSyncStatus(
            provider=connection.account.provider,
            account_id=connection.account.account_id,
            state=EmailSyncRunState.SUCCEEDED,
            mode=EmailSyncMode.FULL_BACKFILL,
            started_at=started_at,
            finished_at=self._clock(),
            page_count=page_count,
            message_count=message_count,
            raw_email_count=self._email_repository.count_raw_emails(
                provider=connection.account.provider,
            ),
        )
        self._set_status(status)
        return status

    async def fetch_retained_bodies(
        self,
        *,
        connection: EmailConnection,
        metadata: Iterable[EmailMessageMetadata],
        candidate_query: EmailCandidateQuery,
        reconciliation_or_debug_refs: Iterable[EmailMessageRef] = (),
        max_body_bytes: int | None = None,
    ) -> EmailBodyBatch:
        """Fetch bodies only for broad candidates or explicit reconciliation refs."""

        selected_refs: list[EmailMessageRef] = []
        seen_message_ids: set[str] = set()

        def select_ref(ref: EmailMessageRef) -> None:
            if ref.message_id in seen_message_ids:
                return
            seen_message_ids.add(ref.message_id)
            selected_refs.append(ref)

        for message in metadata:
            if candidate_query.matches_metadata(message):
                select_ref(message.ref)

        for ref in reconciliation_or_debug_refs:
            select_ref(ref)

        if not selected_refs:
            return EmailBodyBatch(bodies=(), failures=())

        bodies: list[EmailMessageBody] = []
        failures: list[EmailBodyFetchFailure] = []
        for ref_chunk in _chunk_refs(
            selected_refs,
            chunk_size=_retained_body_batch_size(self._body_provider) or len(selected_refs),
        ):
            batch = await self._body_provider.fetch_message_bodies(
                connection,
                EmailBodyFetchRequest(
                    refs=ref_chunk,
                    max_body_bytes=max_body_bytes,
                ),
            )
            bodies.extend(batch.bodies)
            failures.extend(batch.failures)

        return EmailBodyBatch(bodies=tuple(bodies), failures=tuple(failures))

    async def _list_full_backfill_page(
        self,
        connection: EmailConnection,
        *,
        page_token: str | None,
    ) -> EmailMetadataPage:
        return await self._provider.list_message_metadata(
            connection,
            EmailMetadataListRequest(
                mode=EmailSyncMode.FULL_BACKFILL,
                page_size=self._page_size,
                page_token=page_token,
            ),
        )

    async def _run_metadata_pages(
        self,
        *,
        connection: EmailConnection,
        sync_cursor: EmailProviderCursor | None,
        initial_mode: EmailSyncMode | None,
        initial_page_token: str | None,
        started_at: datetime,
    ) -> EmailSyncStatus:
        if self._email_repository is None or self._sync_service is None:
            raise SyncConnectionNotConfiguredError("Sync repositories are not configured.")

        page_token = initial_page_token
        mode = initial_mode
        latest_cursor: EmailProviderCursor | None = (
            sync_cursor
            if initial_mode is EmailSyncMode.FULL_BACKFILL and initial_page_token is not None
            else None
        )
        page_count = 0
        message_count = 0
        recovered_from_expired_cursor = False
        final_mode = (
            EmailSyncMode.INCREMENTAL if sync_cursor is not None else EmailSyncMode.FULL_BACKFILL
        )

        while True:
            page_result = await self.list_metadata_page(
                connection=connection,
                mode=mode,
                sync_cursor=sync_cursor,
                page_token=page_token,
            )
            final_mode = page_result.mode
            recovered_from_expired_cursor = (
                recovered_from_expired_cursor or page_result.recovered_from_expired_cursor
            )
            page_count += 1
            message_count += len(page_result.page.messages)
            if page_result.page.messages:
                self._email_repository.upsert_metadata_only(
                    page_result.page.messages,
                    ingested_at=self._clock(),
                )
                self._persist_filter_decisions(
                    page_result.page.messages,
                    candidate_query=build_broad_candidate_query(),
                )
                if _can_fetch_retained_bodies(self._body_provider):
                    body_batch = await self.fetch_retained_bodies(
                        connection=connection,
                        metadata=page_result.page.messages,
                        candidate_query=build_broad_candidate_query(),
                    )
                    _raise_for_retained_body_failures(body_batch)
                    if body_batch.bodies:
                        self._email_repository.upsert_retained_bodies(
                            body_batch.bodies,
                            retention_state=RawEmailBodyRetentionState.RETAINED,
                        )
            if page_result.page.next_sync_cursor is not None:
                latest_cursor = page_result.page.next_sync_cursor
            self._set_status(
                EmailSyncStatus(
                    provider=connection.account.provider,
                    account_id=connection.account.account_id,
                    state=EmailSyncRunState.RUNNING,
                    mode=final_mode,
                    started_at=started_at,
                    page_count=page_count,
                    message_count=message_count,
                    raw_email_count=self._email_repository.count_raw_emails(
                        provider=connection.account.provider,
                    ),
                    recovered_from_expired_cursor=recovered_from_expired_cursor,
                )
            )
            if page_result.page.next_page_token is None:
                break

            page_token = page_result.page.next_page_token
            mode = page_result.mode
            self._sync_service.store_page_progress(
                connection.account,
                mode=mode,
                next_page_token=page_token,
                sync_cursor=latest_cursor or sync_cursor,
                updated_at=self._clock(),
            )
            if mode is EmailSyncMode.FULL_BACKFILL:
                sync_cursor = None

        if latest_cursor is not None:
            self._sync_service.store_sync_cursor(
                latest_cursor,
                updated_at=self._clock(),
            )
        else:
            self._sync_service.clear_page_progress(
                connection.account,
                updated_at=self._clock(),
            )

        return EmailSyncStatus(
            provider=connection.account.provider,
            account_id=connection.account.account_id,
            state=EmailSyncRunState.SUCCEEDED,
            mode=final_mode,
            started_at=started_at,
            finished_at=self._clock(),
            page_count=page_count,
            message_count=message_count,
            raw_email_count=self._email_repository.count_raw_emails(
                provider=connection.account.provider,
            ),
            recovered_from_expired_cursor=recovered_from_expired_cursor,
        )

    def _persist_filter_decisions(
        self,
        metadata: Iterable[EmailMessageMetadata],
        *,
        candidate_query: EmailCandidateQuery,
    ) -> None:
        if self._filter_decision_repository is None:
            return

        decided_at = self._clock()
        self._filter_decision_repository.upsert_filter_decisions(
            EmailFilterDecisionRecord(
                email_id=message.ref.message_id,
                strategy=decision.strategy.value,
                outcome=decision.outcome,
                reason=decision.reason,
                decided_at=decided_at,
            )
            for message in metadata
            for decision in (candidate_query.evaluate_metadata(message),)
        )


def _retained_body_batch_size(body_provider: RetainedBodyProvider) -> int | None:
    capabilities = getattr(body_provider, "capabilities", None)
    if not isinstance(capabilities, EmailProviderCapabilities):
        return None
    return capabilities.max_body_batch_size


def _can_fetch_retained_bodies(body_provider: object) -> bool:
    return callable(getattr(body_provider, "fetch_message_bodies", None))


def _raise_for_retained_body_failures(body_batch: EmailBodyBatch) -> None:
    if body_batch.failures:
        raise EmailProviderError(
            public_message="One or more retained email bodies could not be fetched."
        )


def _chunk_refs(
    refs: list[EmailMessageRef],
    *,
    chunk_size: int,
) -> tuple[tuple[EmailMessageRef, ...], ...]:
    return tuple(
        tuple(refs[index : index + chunk_size]) for index in range(0, len(refs), chunk_size)
    )


def build_idle_sync_status(*, now: datetime | None = None) -> SyncJobStatus:
    """Build the public status snapshot before any sync job is running."""

    return SyncJobStatus(
        phase=SyncJobPhase.IDLE,
        counts=SyncJobCounts(),
        updated_at=now or datetime.now(UTC),
        progress=0,
    )


class BackfillReconciliationMetrics(BaseModel):
    """Deterministic count comparison for provider pages and local raw email rows."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    provider_page_count: int = Field(ge=0)
    provider_message_count: int = Field(ge=0)
    provider_unique_message_count: int = Field(ge=0)
    provider_duplicate_message_count: int = Field(ge=0)
    local_raw_email_count: int = Field(ge=0)
    local_minus_provider_unique_count: int
    missing_local_message_count: int = Field(ge=0)
    extra_local_message_count: int = Field(ge=0)
    reconciled: bool


def build_backfill_reconciliation_metrics(
    *,
    provider: EmailProviderName,
    email_repository: EmailRepository,
    pages: Iterable[EmailMetadataPage],
) -> BackfillReconciliationMetrics:
    """Build Phase 1 backfill reconciliation metrics from provider metadata pages."""

    page_tuple = tuple(pages)
    provider_message_ids: list[str] = []

    for page in page_tuple:
        for message in page.messages:
            provider_message_ids.append(message.ref.message_id)

    provider_message_count = len(provider_message_ids)
    provider_unique_message_ids = set(provider_message_ids)
    provider_unique_message_count = len(provider_unique_message_ids)
    local_raw_email_count = email_repository.count_raw_emails(provider=provider)
    local_raw_email_ids = set(email_repository.list_raw_email_ids(provider=provider))
    local_minus_provider_unique_count = local_raw_email_count - provider_unique_message_count
    missing_local_message_count = len(provider_unique_message_ids - local_raw_email_ids)
    extra_local_message_count = len(local_raw_email_ids - provider_unique_message_ids)

    return BackfillReconciliationMetrics(
        provider=provider,
        provider_page_count=len(page_tuple),
        provider_message_count=provider_message_count,
        provider_unique_message_count=provider_unique_message_count,
        provider_duplicate_message_count=(provider_message_count - provider_unique_message_count),
        local_raw_email_count=local_raw_email_count,
        local_minus_provider_unique_count=local_minus_provider_unique_count,
        missing_local_message_count=missing_local_message_count,
        extra_local_message_count=extra_local_message_count,
        reconciled=(missing_local_message_count == 0 and extra_local_message_count == 0),
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _public_sync_error_message(error: Exception) -> str:
    if isinstance(error, EmailProviderError):
        return error.public_message
    return "Sync failed."
