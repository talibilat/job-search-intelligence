from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_application_correction_service,
    get_application_detail_service,
    get_manual_merge_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.models import (
    ApplicationMergeRequest,
    ApplicationMergeResponse,
    ApplicationRecord,
    ApplicationSplitRequest,
    ApplicationSplitResponse,
)
from app.services.application_corrections import (
    ApplicationCorrectionService,
    ApplicationSplitConflictError,
    ApplicationNotFoundError as ApplicationSplitNotFoundError,
)
from app.services.applications import (
    ApplicationDetailService,
    ApplicationNotFoundError as ApplicationDetailNotFoundError,
)
from app.services.manual_merge import (
    ManualApplicationMergeService,
    ManualMergeInvalidRequestError,
    ManualMergeNotFoundError,
)

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get(
    "/{id}",
    response_model=ApplicationRecord,
    responses={404: {"model": ApiErrorResponse}},
    summary="Get Application Detail",
    description="Returns one canonical application row from the local SQLite source of truth.",
)
def get_application_detail(
    id: str,
    service: Annotated[
        ApplicationDetailService,
        Depends(get_application_detail_service),
    ],
) -> ApplicationRecord:
    try:
        return service.get_application(id)
    except ApplicationDetailNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application not found.",
        ) from error


@router.post(
    "/{application_id}/split",
    response_model=ApplicationSplitResponse,
    summary="Split Application",
    description=(
        "Splits selected events out of an incorrectly grouped application into a "
        "new application and records an audited manual correction."
    ),
    responses={
        404: {"model": ApiErrorResponse, "description": "Application not found."},
        409: {"model": ApiErrorResponse, "description": "Application split conflict."},
    },
)
async def split_application(
    application_id: str,
    request: ApplicationSplitRequest,
    correction_service: Annotated[
        ApplicationCorrectionService,
        Depends(get_application_correction_service),
    ],
) -> ApplicationSplitResponse:
    try:
        return correction_service.split_application(
            application_id=application_id,
            request=request,
        )
    except ApplicationSplitNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message=error.public_message,
        ) from error
    except ApplicationSplitConflictError as error:
        raise ApiError(
            status_code=409,
            code=ApiErrorCode.CONFLICT,
            message=error.public_message,
        ) from error


@router.post(
    "/{application_id}/merge",
    response_model=ApplicationMergeResponse,
    responses={
        400: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
    summary="Merge Duplicate Applications",
    description=(
        "Moves events from a duplicate source application into the target application, "
        "deletes the source application, and records an audited merge correction."
    ),
)
async def merge_application(
    application_id: str,
    request: ApplicationMergeRequest,
    merge_service: Annotated[
        ManualApplicationMergeService,
        Depends(get_manual_merge_service),
    ],
) -> ApplicationMergeResponse:
    try:
        return merge_service.merge_applications(
            target_application_id=application_id,
            source_application_id=request.source_application_id,
            reason=request.reason,
        )
    except ManualMergeInvalidRequestError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message="Cannot merge an application into itself.",
        ) from error
    except ManualMergeNotFoundError as error:
        label = "Target" if error.role == "target" else "Source"
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message=f"{label} application was not found.",
        ) from error
