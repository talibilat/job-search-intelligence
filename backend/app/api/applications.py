from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_application_detail_service,
    get_application_events_service,
    get_manual_edit_service,
    get_manual_merge_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.models import (
    ApplicationEventEditRequest,
    ApplicationEventEditResponse,
    ApplicationEventRecord,
    ApplicationMergeRequest,
    ApplicationMergeResponse,
    ApplicationRecord,
    ApplicationStatusEditRequest,
    ApplicationStatusEditResponse,
)
from app.services.applications import (
    ApplicationDetailService,
    ApplicationEventsService,
    ApplicationNotFoundError,
)
from app.services.manual_edit import (
    ManualApplicationEditService,
    ManualEditInvalidRequestError,
    ManualEditNotFoundError,
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
    except ApplicationNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application not found.",
        ) from error


@router.get(
    "/{id}/events",
    response_model=list[ApplicationEventRecord],
    responses={404: {"model": ApiErrorResponse}},
    summary="List Application Events",
    description="Returns the canonical event timeline for one application from local SQLite.",
)
def get_application_events(
    id: str,
    service: Annotated[
        ApplicationEventsService,
        Depends(get_application_events_service),
    ],
) -> list[ApplicationEventRecord]:
    try:
        return service.list_application_events(id)
    except ApplicationNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application not found.",
        ) from error


@router.patch(
    "/{application_id}/status",
    response_model=ApplicationStatusEditResponse,
    responses={
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
    summary="Edit Application Status",
    description=(
        "Manually corrects one application's current status, locks it from automatic "
        "overwrite, and records an audited status_edit correction."
    ),
)
def edit_application_status(
    application_id: str,
    request: ApplicationStatusEditRequest,
    edit_service: Annotated[
        ManualApplicationEditService,
        Depends(get_manual_edit_service),
    ],
) -> ApplicationStatusEditResponse:
    try:
        return edit_service.edit_status(
            application_id=application_id,
            current_status=request.current_status,
            reason=request.reason,
        )
    except ManualEditNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application was not found.",
        ) from error


@router.patch(
    "/{application_id}/events/{event_id}",
    response_model=ApplicationEventEditResponse,
    responses={
        400: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
    summary="Edit Application Event",
    description=(
        "Manually corrects one timeline event, locks the application from automatic "
        "overwrite, and records an audited event_edit correction."
    ),
)
def edit_application_event(
    application_id: str,
    event_id: str,
    request: ApplicationEventEditRequest,
    edit_service: Annotated[
        ManualApplicationEditService,
        Depends(get_manual_edit_service),
    ],
) -> ApplicationEventEditResponse:
    try:
        return edit_service.edit_event(
            application_id=application_id,
            event_id=event_id,
            event_type=request.event_type,
            event_at=request.event_at,
            email_id=request.email_id,
            extract_note=request.extract_note,
            update_email_id="email_id" in request.model_fields_set,
            update_extract_note="extract_note" in request.model_fields_set,
            reason=request.reason,
        )
    except ManualEditInvalidRequestError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message="Application event edit is invalid.",
        ) from error
    except ManualEditNotFoundError as error:
        message = (
            "Application was not found."
            if error.resource == "application"
            else "Application event was not found."
        )
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message=message,
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
