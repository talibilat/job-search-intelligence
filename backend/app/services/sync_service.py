from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from app.config import EmailProviderName
from app.db.repositories import BackfillStateRepository, EmailRepository
from app.db.repositories.sync_state import SyncStateRepository
from app.models import SyncJobCounts, SyncJobPhase, SyncJobStatus
from app.models.records import EmailBackfillStateRecord, EmailBackfillStatus, EmailSyncStateRecord
from app.providers.email import (
    EmailAccountRef,
    EmailConnection,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCursor,
    EmailProviderError,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
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


class SyncService:
    """Business seam for email sync state used by full and incremental runs."""

    def __init__(self, *, sync_state_repository: SyncStateRepository) -> None:
        self._sync_state_repository = sync_state_repository

    def get_sync_cursor(self, account: EmailAccountRef) -> EmailProviderCursor | None:
        return self._sync_state_repository.get_cursor(account)

    def get_sync_status(self, account: EmailAccountRef) -> EmailSyncStateStatus | None:
        state = self._sync_state_repository.fetch_state(account)
        if state is None:
            return None

        return EmailSyncStateStatus(
            account=EmailAccountRef(
                provider=EmailProviderName(state.provider),
                account_id=state.account_id,
            ),
            cursor=EmailProviderCursor(
                account=EmailAccountRef(
                    provider=EmailProviderName(state.provider),
                    account_id=state.account_id,
                ),
                value=state.sync_cursor,
                issued_at=state.cursor_issued_at,
            ),
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


class EmailSyncStateStatus(BaseModel):
    """Persisted sync cursor snapshot for service-level status checks."""

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    cursor: EmailProviderCursor | None
    last_state_update_at: datetime


class BackfillStateService:
    """Business seam for durable full-backfill progress and resumability."""

    def __init__(self, *, backfill_state_repository: BackfillStateRepository) -> None:
        self._backfill_state_repository = backfill_state_repository

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
        updated_at: datetime,
    ) -> EmailBackfillStateRecord:
        existing = self._backfill_state_repository.fetch_state(account)
        if existing is None:
            existing = self.start_or_resume_backfill(account, started_at=updated_at)

        sync_cursor = existing.sync_cursor
        cursor_issued_at = existing.cursor_issued_at
        if page.next_sync_cursor is not None:
            sync_cursor = page.next_sync_cursor.value
            cursor_issued_at = page.next_sync_cursor.issued_at

        status = (
            EmailBackfillStatus.RUNNING
            if page.next_page_token is not None
            else EmailBackfillStatus.COMPLETED
        )
        return self._backfill_state_repository.save_state(
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


class EmailSyncPageResult(BaseModel):
    """One metadata sync page plus the mode that produced it."""

    model_config = ConfigDict(frozen=True)

    mode: EmailSyncMode
    page: EmailMetadataPage
    recovered_from_expired_cursor: bool = False


class EmailBackfillPageResult(BaseModel):
    """One persisted full-backfill page plus the durable state after it."""

    model_config = ConfigDict(frozen=True)

    mode: EmailSyncMode = EmailSyncMode.FULL_BACKFILL
    page: EmailMetadataPage
    state: EmailBackfillStateRecord


class EmailSyncService:
    """Service-layer coordination for resumable provider metadata sync."""

    def __init__(self, *, provider: MetadataListingProvider, page_size: int) -> None:
        if page_size < 1:
            msg = "page_size must be at least 1"
            raise ValueError(msg)
        self._provider = provider
        self._page_size = page_size

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
            state=backfill_state_service.record_backfill_page(
                connection.account,
                page=page,
                updated_at=timestamp,
            ),
        )

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
