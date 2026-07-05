from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import get_gmail_secret_store
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.db.repositories import (
    BackfillStateRepository,
    EmailConnectionRepository,
    EmailRepository,
    SyncStateRepository,
)
from app.db.sqlite_url import sqlite_database_path
from app.models.records import EmailBackfillStatus
from app.providers.email import EmailConnection, EmailProvider
from app.providers.email.gmail import GmailEmailProvider
from app.security import SecretStore
from app.services.sync_service import (
    BackfillStateService,
    EmailSyncRunState,
    EmailSyncRuntime,
    EmailSyncService,
    EmailSyncStatus,
    SyncAlreadyRunningError,
    SyncConnectionNotConfiguredError,
    SyncService,
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

    async def run_manual_sync(self) -> EmailSyncStatus:
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
                sync_state_service = SyncService(
                    sync_state_repository=sync_state_repository,
                )
                sync_service = EmailSyncService(
                    provider=self._email_provider,
                    page_size=self._settings.gmail_page_size,
                    email_repository=email_repository,
                    sync_service=sync_state_service,
                    status_callback=self._status_store.set_status,
                )
                backfill_state = backfill_state_repository.fetch_state(connection.account)
                sync_cursor = sync_state_repository.get_cursor(connection.account)
                should_run_full_backfill = sync_cursor is None or (
                    backfill_state is not None
                    and backfill_state.status is not EmailBackfillStatus.COMPLETED
                )
                if should_run_full_backfill:
                    return await sync_service.run_full_backfill(
                        connection=connection,
                        backfill_state_service=BackfillStateService(
                            backfill_state_repository=backfill_state_repository,
                            sync_state_repository=sync_state_repository,
                        ),
                    )
                return await sync_service.run_manual_sync(connection=connection)
        finally:
            self._status_store.release_run()

    def current_status(self) -> EmailSyncStatus:
        return self._status_store.current_status()


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
        try:
            return EmailConnectionRepository(sqlite_connection).fetch_default_connection_metadata(
                settings.email_provider,
            )
        except sqlite3.OperationalError as error:
            if "no such table: email_connections" in str(error):
                return None
            raise


def get_email_sync_connection_resolver(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> EmailSyncConnectionResolver:
    return lambda: resolve_email_sync_connection(settings)


def get_sync_status_store() -> EmailSyncStatusStore:
    return _sync_status_store


def get_email_sync_runtime(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_provider: Annotated[EmailProvider, Depends(get_sync_email_provider)],
    connection_resolver: Annotated[
        EmailSyncConnectionResolver,
        Depends(get_email_sync_connection_resolver),
    ],
    status_store: Annotated[EmailSyncStatusStore, Depends(get_sync_status_store)],
) -> EmailSyncRuntime:
    return ConfiguredEmailSyncRuntime(
        settings=settings,
        email_provider=email_provider,
        connection_resolver=connection_resolver,
        status_store=status_store,
    )


@router.post(
    "",
    response_model=EmailSyncStatus,
    responses={
        400: {"model": ApiErrorResponse},
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        429: {"model": ApiErrorResponse},
        502: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def sync_now(
    sync_runtime: Annotated[EmailSyncRuntime, Depends(get_email_sync_runtime)],
) -> EmailSyncStatus:
    try:
        return await sync_runtime.run_manual_sync()
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
