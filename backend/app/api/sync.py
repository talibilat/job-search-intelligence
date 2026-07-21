from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from pydantic import ValidationError

from app.api.auth import get_gmail_secret_store
from app.api.dependencies import get_readonly_email_repository
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.db.repositories import (
    BackfillStateRepository,
    EmailConnectionRepository,
    EmailFilterDecisionRepository,
    EmailRepository,
    SyncStateRepository,
)
from app.db.sqlite_url import sqlite_database_path
from app.models.raw_email import (
    MAX_EMAIL_PREVIEW_PAGE_SIZE,
    RawEmailDetail,
    RawEmailPreviewOrder,
    RawEmailPreviewPage,
)
from app.models.records import EmailBackfillStatus, RawEmailPreviewRecord
from app.models.sync import SyncLocalStats, SyncScopeEstimate
from app.providers.email import (
    EmailConnection,
    EmailProvider,
    EmailProviderAuthError,
    EmailProviderError,
)
from app.providers.email.gmail import GmailEmailProvider
from app.security import SecretStore
from app.services.sync_service import (
    BackfillStateService,
    EmailSyncOptions,
    EmailSyncPreviewService,
    EmailSyncRunState,
    EmailSyncRuntime,
    EmailSyncService,
    EmailSyncStatus,
    SyncAlreadyRunningError,
    SyncConnectionNotConfiguredError,
    SyncJob,
    SyncService,
    build_sync_local_stats,
    build_sync_scope_estimate,
    latest_sync_run_at,
)
from app.services.synced_email_reader import (
    SyncedEmailConnectionRequiredError,
    SyncedEmailContentUnavailableError,
    SyncedEmailNotFoundError,
    SyncedEmailReaderService,
)

router = APIRouter(prefix="/sync", tags=["sync"])
EmailSyncConnectionResolver = Callable[[], EmailConnection | None]


class EmailSyncStatusStore:
    def __init__(self) -> None:
        self._status = EmailSyncStatus(state=EmailSyncRunState.IDLE)
        self._run_lock = threading.Lock()

    def try_acquire_run(self) -> bool:
        return self._run_lock.acquire(blocking=False)

    def release_run(self) -> None:
        self._run_lock.release()

    def set_status(self, status: EmailSyncStatus) -> None:
        self._status = status

    def current_status(self) -> EmailSyncStatus:
        return self._status


class ConfiguredEmailSyncRuntime:
    def __init__(
        self,
        *,
        settings: AppSettings,
        email_provider: EmailProvider,
        connection_resolver: EmailSyncConnectionResolver,
        status_store: EmailSyncStatusStore,
    ) -> None:
        self._settings = settings
        self._email_provider = email_provider
        self._connection_resolver = connection_resolver
        self._status_store = status_store

    async def run_manual_sync(self, options: EmailSyncOptions | None = None) -> EmailSyncStatus:
        sync_options = options or EmailSyncOptions()
        connection = self._connection_resolver()
        if connection is None:
            raise SyncConnectionNotConfiguredError("Gmail connection is not configured yet.")
        if not self._status_store.try_acquire_run():
            raise SyncAlreadyRunningError("Email sync is already running.")

        try:
            database_path = sqlite_database_path(self._settings.database_url)
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database_path) as sqlite_connection:
                sync_state_repository = SyncStateRepository(sqlite_connection)
                backfill_state_repository = BackfillStateRepository(sqlite_connection)
                email_repository = EmailRepository(sqlite_connection)
                filter_decision_repository = EmailFilterDecisionRepository(sqlite_connection)
                sync_state_service = SyncService(
                    sync_state_repository=sync_state_repository,
                )
                sync_service = EmailSyncService(
                    provider=self._email_provider,
                    page_size=self._settings.gmail_page_size,
                    email_repository=email_repository,
                    filter_decision_repository=filter_decision_repository,
                    sync_service=sync_state_service,
                    status_callback=self._status_store.set_status,
                )
                backfill_state = backfill_state_repository.fetch_state(connection.account)
                sync_cursor = sync_state_repository.get_cursor(connection.account)
                should_run_full_backfill = (
                    sync_cursor is None
                    or backfill_state is None
                    or backfill_state.status is not EmailBackfillStatus.COMPLETED
                )
                try:
                    if sync_options.is_windowed:
                        return await sync_service.run_manual_sync(
                            connection=connection,
                            options=sync_options,
                        )
                    if should_run_full_backfill:
                        return await sync_service.run_full_backfill(
                            connection=connection,
                            backfill_state_service=BackfillStateService(
                                backfill_state_repository=backfill_state_repository,
                                sync_state_repository=sync_state_repository,
                            ),
                            options=sync_options,
                        )
                    return await sync_service.run_manual_sync(
                        connection=connection,
                        options=sync_options,
                    )
                except EmailProviderAuthError:
                    EmailConnectionRepository(sqlite_connection).mark_reauth_required(
                        connection.account
                    )
                    raise
        finally:
            self._status_store.release_run()

    def current_status(self) -> EmailSyncStatus:
        return self._status_store.current_status()

    def recent_email_previews(
        self,
        *,
        limit: int = 10,
        order: RawEmailPreviewOrder = RawEmailPreviewOrder.SENT_AT,
    ) -> tuple[RawEmailPreviewRecord, ...]:
        database_path = sqlite_database_path(self._settings.database_url)
        if not database_path.exists():
            return ()

        with sqlite3.connect(database_path) as sqlite_connection:
            return EmailSyncPreviewService(
                email_repository=EmailRepository(sqlite_connection),
            ).list_recent_email_previews(
                provider=self._settings.email_provider,
                limit=limit,
                order=order,
            )


_sync_status_store = EmailSyncStatusStore()


def get_sync_email_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
    secret_store: Annotated[SecretStore, Depends(get_gmail_secret_store)],
) -> EmailProvider:
    return GmailEmailProvider(settings=settings, secret_store=secret_store)


def resolve_email_sync_connection(settings: AppSettings) -> EmailConnection | None:
    database_path = sqlite_database_path(settings.database_url)
    if not database_path.exists():
        return None

    with sqlite3.connect(database_path) as sqlite_connection:
        return EmailConnectionRepository(sqlite_connection).fetch_default_connection_metadata(
            settings.email_provider,
        )


def get_email_sync_connection_resolver(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> EmailSyncConnectionResolver:
    return lambda: resolve_email_sync_connection(settings)


def get_sync_status_store() -> EmailSyncStatusStore:
    return _sync_status_store


def build_configured_email_sync_runtime(
    settings: AppSettings,
    *,
    email_provider: EmailProvider | None = None,
    connection_resolver: EmailSyncConnectionResolver | None = None,
    status_store: EmailSyncStatusStore | None = None,
) -> ConfiguredEmailSyncRuntime:
    resolved_email_provider = email_provider or get_sync_email_provider(
        settings,
        get_gmail_secret_store(settings),
    )
    return ConfiguredEmailSyncRuntime(
        settings=settings,
        email_provider=resolved_email_provider,
        connection_resolver=connection_resolver or get_email_sync_connection_resolver(settings),
        status_store=status_store or get_sync_status_store(),
    )


def create_configured_sync_job(settings: AppSettings) -> SyncJob:
    async def run_configured_sync() -> None:
        runtime = build_configured_email_sync_runtime(settings)
        try:
            await runtime.run_manual_sync()
        except (EmailProviderError, SyncConnectionNotConfiguredError):
            return

    return run_configured_sync


def get_email_sync_runtime(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_provider: Annotated[EmailProvider, Depends(get_sync_email_provider)],
    connection_resolver: Annotated[
        EmailSyncConnectionResolver,
        Depends(get_email_sync_connection_resolver),
    ],
    status_store: Annotated[EmailSyncStatusStore, Depends(get_sync_status_store)],
) -> EmailSyncRuntime:
    return build_configured_email_sync_runtime(
        settings,
        email_provider=email_provider,
        connection_resolver=connection_resolver,
        status_store=status_store,
    )


def get_synced_email_reader_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[EmailRepository, Depends(get_readonly_email_repository)],
    email_provider: Annotated[EmailProvider, Depends(get_sync_email_provider)],
    connection_resolver: Annotated[
        EmailSyncConnectionResolver,
        Depends(get_email_sync_connection_resolver),
    ],
) -> SyncedEmailReaderService:
    connection = connection_resolver()
    return SyncedEmailReaderService(
        repository=email_repository,
        provider=email_provider,
        connection=connection,
        provider_name=settings.email_provider,
    )


@router.post(
    "",
    response_model=EmailSyncStatus,
    responses={
        400: {"model": ApiErrorResponse},
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        429: {"model": ApiErrorResponse},
        502: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def sync_now(
    sync_runtime: Annotated[EmailSyncRuntime, Depends(get_email_sync_runtime)],
    options: Annotated[EmailSyncOptions | None, Body()] = None,
) -> EmailSyncStatus:
    try:
        return await sync_runtime.run_manual_sync(options)
    except SyncConnectionNotConfiguredError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=str(error),
        ) from error
    except SyncAlreadyRunningError as error:
        raise ApiError(
            status_code=409,
            code=ApiErrorCode.CONFLICT,
            message=str(error),
        ) from error


@router.get("/status", response_model=EmailSyncStatus)
def sync_status(
    sync_runtime: Annotated[EmailSyncRuntime, Depends(get_email_sync_runtime)],
) -> EmailSyncStatus:
    """Report the current email sync job status without exposing provider payloads."""

    return sync_runtime.current_status()


@router.get("/recent-emails", response_model=list[RawEmailPreviewRecord])
def sync_recent_emails(
    sync_runtime: Annotated[EmailSyncRuntime, Depends(get_email_sync_runtime)],
    limit: int = 10,
    order: RawEmailPreviewOrder = RawEmailPreviewOrder.SENT_AT,
) -> list[RawEmailPreviewRecord]:
    """Return recently stored raw-email metadata without body text.

    ``order=sent_at`` (default) shows the newest synced mailbox messages;
    ``order=ingested_at`` is the diagnostic view of what the latest sync wrote.
    """

    return list(sync_runtime.recent_email_previews(limit=limit, order=order))


@router.get(
    "/emails",
    response_model=RawEmailPreviewPage,
    responses={422: {"model": ApiErrorResponse}},
    summary="List Synced Emails",
    description=(
        "Returns a deterministic page of locally synced raw-email metadata "
        "within an optional sent-date window. Never contacts the email "
        "provider or triggers classification."
    ),
)
def sync_emails(
    email_repository: Annotated[EmailRepository, Depends(get_readonly_email_repository)],
    settings: Annotated[AppSettings, Depends(get_settings)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_EMAIL_PREVIEW_PAGE_SIZE)] = 10,
    sent_after: Annotated[datetime | None, Query()] = None,
    sent_before: Annotated[datetime | None, Query()] = None,
) -> RawEmailPreviewPage:
    for bound in (sent_after, sent_before):
        if bound is not None and bound.tzinfo is None:
            raise ApiError(
                status_code=422,
                code=ApiErrorCode.VALIDATION_ERROR,
                message="sent_after and sent_before must be timezone-aware.",
            )
    return email_repository.paginate_email_previews(
        provider=settings.email_provider,
        page=page,
        page_size=page_size,
        sent_after=sent_after,
        sent_before=sent_before,
    )


@router.get(
    "/emails/{public_id}/content",
    response_model=RawEmailDetail,
    responses={
        400: {"model": ApiErrorResponse},
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        429: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    summary="Read Synced Email Content",
    description=(
        "Returns normalized plain-text content for one synced email. Retained "
        "bodies are served from local storage; metadata-only messages are "
        "fetched transiently from the email provider and are not persisted."
    ),
)
async def sync_email_content(
    public_id: str,
    reader_service: Annotated[
        SyncedEmailReaderService,
        Depends(get_synced_email_reader_service),
    ],
) -> RawEmailDetail:
    try:
        return await reader_service.read_email(public_id)
    except SyncedEmailNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Email not found.",
        ) from error
    except SyncedEmailContentUnavailableError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Email content is not available.",
        ) from error
    except SyncedEmailConnectionRequiredError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message="No Gmail connection is configured.",
        ) from error


@router.get(
    "/stats",
    response_model=SyncLocalStats,
    summary="Get Local Sync Stats",
    description=(
        "Returns deterministic totals over locally stored raw-email metadata "
        "plus the latest persisted or in-process sync run timestamp."
    ),
)
def sync_stats(
    email_repository: Annotated[EmailRepository, Depends(get_readonly_email_repository)],
    sync_runtime: Annotated[EmailSyncRuntime, Depends(get_email_sync_runtime)],
) -> SyncLocalStats:
    connection = email_repository.connection
    return build_sync_local_stats(
        email_repository=email_repository,
        last_run_at=latest_sync_run_at(
            sync_runtime.current_status().finished_at,
            SyncStateRepository(connection).latest_update_at(),
            BackfillStateRepository(connection).latest_completed_at(),
        ),
    )


@router.get(
    "/estimate",
    response_model=SyncScopeEstimate,
    responses={422: {"model": ApiErrorResponse}},
    summary="Estimate Sync Scope",
    description=(
        "Returns a deterministic local approximation of how much email a sync "
        "scope covers, using already-synced metadata only. It never calls the "
        "email provider."
    ),
)
def sync_estimate(
    email_repository: Annotated[EmailRepository, Depends(get_readonly_email_repository)],
    settings: Annotated[AppSettings, Depends(get_settings)],
    max_messages: Annotated[int | None, Query(ge=1, le=100_000)] = None,
    since_date: Annotated[date | None, Query()] = None,
    before_date: Annotated[date | None, Query()] = None,
    max_age_days: Annotated[int | None, Query(ge=1, le=3650)] = None,
) -> SyncScopeEstimate:
    try:
        options = EmailSyncOptions(
            max_messages=max_messages,
            since_date=since_date,
            before_date=before_date,
            max_age_days=max_age_days,
        )
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Sync estimate request validation failed.",
        ) from error
    connection = email_repository.connection
    email_connection = EmailConnectionRepository(connection).fetch_default_connection_metadata(
        settings.email_provider,
    )
    requires_full_backfill = True
    if email_connection is not None:
        backfill_state = BackfillStateRepository(connection).fetch_state(email_connection.account)
        sync_cursor = SyncStateRepository(connection).get_cursor(email_connection.account)
        requires_full_backfill = (
            sync_cursor is None
            or backfill_state is None
            or backfill_state.status is not EmailBackfillStatus.COMPLETED
        )

    return build_sync_scope_estimate(
        options=options,
        email_repository=email_repository,
        now=datetime.now(UTC),
        requires_full_backfill=requires_full_backfill,
    )
