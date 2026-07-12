from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_email_connection_secret_refs
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.api.sync import EmailSyncStatusStore, get_sync_status_store
from app.config import AppSettings, get_settings
from app.models import WipeDataRequest, WipeDataResponse
from app.security import SecretRef, SecretStore, create_secret_store
from app.services.wipe_data import (
    UnsafeWipeTargetError,
    WipeSecretDeletionError,
    wipe_local_data,
)

router = APIRouter(prefix="/local-data", tags=["local-data"])


def get_wipe_secret_store(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SecretStore:
    return create_secret_store(settings)


async def get_wipe_operation(
    status_store: Annotated[EmailSyncStatusStore, Depends(get_sync_status_store)],
) -> AsyncIterator[None]:
    if not status_store.try_acquire_run():
        raise ApiError(
            status_code=409,
            code=ApiErrorCode.CONFLICT,
            message="Email sync or local data deletion is already running. Try again later.",
        )
    try:
        yield
    finally:
        status_store.release_run()


def get_locked_email_connection_secret_refs(
    _operation: Annotated[None, Depends(get_wipe_operation)],
    connection_secret_refs: Annotated[
        list[SecretRef],
        Depends(get_email_connection_secret_refs),
    ],
) -> list[SecretRef]:
    return connection_secret_refs


@router.post(
    "/wipe",
    response_model=WipeDataResponse,
    summary="Wipe local app data",
    description=(
        "Deletes configured local JobTracker data and derived artifacts after "
        "the request body confirms the exact wipe-local-data phrase. The "
        "service preflights every filesystem target and returns a typed 400 "
        "error instead of deleting anything when a target is unsafe."
    ),
    responses={
        400: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def wipe_data(
    request: WipeDataRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
    connection_secret_refs: Annotated[
        list[SecretRef],
        Depends(get_locked_email_connection_secret_refs),
    ],
    secret_store: Annotated[SecretStore, Depends(get_wipe_secret_store)],
) -> WipeDataResponse:
    del request
    try:
        result = await wipe_local_data(
            settings,
            secret_store=secret_store,
            connection_secret_refs=connection_secret_refs,
        )
    except UnsafeWipeTargetError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message="Configured local data path is not safe to wipe.",
        ) from error
    except WipeSecretDeletionError as error:
        raise ApiError(
            status_code=503,
            code=ApiErrorCode.SERVICE_UNAVAILABLE,
            message="Stored credentials could not be deleted. Local data was not changed.",
        ) from error

    return WipeDataResponse(
        status="wiped",
        deleted_paths=result.deleted_paths,
        missing_paths=result.missing_paths,
    )
