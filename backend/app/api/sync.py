from __future__ import annotations

import sqlite3
import threading
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.db.repositories import EmailRepository, SyncStateRepository
from app.db.sqlite_url import sqlite_database_path
from app.providers.email import EmailConnection, EmailProvider
from app.providers.email.gmail import GmailEmailProvider
from app.services.sync_service import (
    EmailSyncRunState,
    EmailSyncRuntime,
    EmailSyncService,
    EmailSyncStatus,
    SyncAlreadyRunningError,
    SyncConnectionNotConfiguredError,
    SyncService,
)

router = APIRouter(prefix="/sync", tags=["sync"])


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
        connection: EmailConnection | None,
        status_store: EmailSyncStatusStore,
    ) -> None:
        self._settings = settings
        self._email_provider = email_provider
        self._connection = connection
        self._status_store = status_store

    async def run_manual_sync(self) -> EmailSyncStatus:
        if self._connection is None:
            raise SyncConnectionNotConfiguredError("Gmail connection is not configured yet.")
        if not self._status_store.try_acquire_run():
            raise SyncAlreadyRunningError("Email sync is already running.")

        try:
            database_path = sqlite_database_path(self._settings.database_url)
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database_path) as sqlite_connection:
                sync_service = EmailSyncService(
                    provider=self._email_provider,
                    page_size=self._settings.gmail_page_size,
                    email_repository=EmailRepository(sqlite_connection),
                    sync_service=SyncService(
                        sync_state_repository=SyncStateRepository(sqlite_connection),
                    ),
                    status_callback=self._status_store.set_status,
                )
                return await sync_service.run_manual_sync(connection=self._connection)
        finally:
            self._status_store.release_run()

    def current_status(self) -> EmailSyncStatus:
        return self._status_store.current_status()


_sync_status_store = EmailSyncStatusStore()


def get_sync_email_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> EmailProvider:
    return GmailEmailProvider(settings=settings)


def get_email_sync_connection() -> EmailConnection | None:
    return None


def get_sync_status_store() -> EmailSyncStatusStore:
    return _sync_status_store


def get_email_sync_runtime(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_provider: Annotated[EmailProvider, Depends(get_sync_email_provider)],
    connection: Annotated[EmailConnection | None, Depends(get_email_sync_connection)],
    status_store: Annotated[EmailSyncStatusStore, Depends(get_sync_status_store)],
) -> EmailSyncRuntime:
    return ConfiguredEmailSyncRuntime(
        settings=settings,
        email_provider=email_provider,
        connection=connection,
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
