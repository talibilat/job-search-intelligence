from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.models import SetupStatusResponse, SetupSubmitRequest, SetupSubmitResponse
from app.services.setup_status import build_setup_status
from app.services.setup_submission import SetupSubmissionValidationError, submit_setup

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SetupStatusResponse:
    """Report the Phase 0 setup shell without validating or exposing secrets."""

    return build_setup_status(settings)


@router.post(
    "",
    response_model=SetupSubmitResponse,
    summary="Submit first-run setup choices",
    description=(
        "Accepts non-secret Phase 0 setup choices and validates selected provider "
        "metadata without running provider auth flows or persisting secrets."
    ),
    responses={400: {"model": ApiErrorResponse}},
)
async def setup_submit(
    request: SetupSubmitRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SetupSubmitResponse:
    try:
        return submit_setup(request, settings)
    except SetupSubmissionValidationError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.message,
            details=[
                ApiErrorDetail(
                    field=setting,
                    message="Required for selected provider.",
                    type="missing_provider_setting",
                )
                for setting in error.missing_settings
            ],
        ) from error
