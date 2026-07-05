from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.providers.email import EmailProviderError
from app.services.sync_service import (
    EmailSyncRunState,
    EmailSyncRuntime,
    EmailSyncStatus,
    SyncAlreadyRunningError,
    SyncConnectionNotConfiguredError,
)

router = APIRouter(prefix="/sync", tags=["sync"])


class UnconfiguredEmailSyncRuntime:
    async def run_manual_sync(self) -> EmailSyncStatus:
        raise SyncConnectionNotConfiguredError("Gmail connection is not configured yet.")

    def current_status(self) -> EmailSyncStatus:
        return EmailSyncStatus(state=EmailSyncRunState.IDLE)


_unconfigured_sync_runtime = UnconfiguredEmailSyncRuntime()


def get_email_sync_runtime() -> EmailSyncRuntime:
    return _unconfigured_sync_runtime


@router.post(
    "",
    response_model=EmailSyncStatus,
    responses={400: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}},
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
    except EmailProviderError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.public_message,
        ) from error


@router.get("/status", response_model=EmailSyncStatus)
def sync_status(
    sync_runtime: Annotated[EmailSyncRuntime, Depends(get_email_sync_runtime)],
) -> EmailSyncStatus:
    return sync_runtime.current_status()
