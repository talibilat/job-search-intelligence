from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.errors import ApiError, ApiErrorCode
from app.config import AppSettings, get_settings
from app.models import WipeDataRequest, WipeDataResponse
from app.services.wipe_data import UnsafeWipeTargetError, wipe_local_data

router = APIRouter(prefix="/local-data", tags=["local-data"])


@router.post("/wipe", response_model=WipeDataResponse)
async def wipe_data(
    request: WipeDataRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> WipeDataResponse:
    del request
    try:
        result = wipe_local_data(settings)
    except UnsafeWipeTargetError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message="Configured local data path is not safe to wipe.",
        ) from error

    return WipeDataResponse(
        status="wiped",
        deleted_paths=result.deleted_paths,
        missing_paths=result.missing_paths,
    )
