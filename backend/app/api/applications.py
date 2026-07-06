from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_application_correction_service,
    get_application_detail_service,
    get_application_events_service,
    get_manual_edit_service,
    get_manual_merge_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.models import (
    ApplicationEventEditRequest,
    ApplicationEventEditResponse,
    ApplicationEventRecord,
    ApplicationMergeRequest,
    ApplicationMergeResponse,
    ApplicationRecord,
    ApplicationSplitRequest,
    ApplicationSplitResponse,
    ApplicationStatusEditRequest,
    ApplicationStatusEditResponse,
)
from app.models.records import ApplicationSource, ApplicationStatus, SponsorshipStatus, WorkMode
from app.services.application_corrections import (
    ApplicationCorrectionService,
    ApplicationSplitConflictError,
)
from app.services.application_corrections import (
    ApplicationNotFoundError as ApplicationSplitNotFoundError,
)
from app.services.applications import (
    ApplicationDetailService,
    ApplicationEventsService,
    ApplicationFilterValidationError,
)
from app.services.applications import (
    ApplicationNotFoundError as ApplicationReadNotFoundError,
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
    "",
    response_model=list[ApplicationRecord],
    summary="List Applications",
    description=(
        "Returns canonical application rows from the local SQLite source of truth, "
        "optionally filtered by status, source, sponsorship, first-seen date range, "
        "role title, salary band, and work mode."
    ),
    responses={422: {"model": ApiErrorResponse}},
)
def list_applications(
    service: Annotated[
        ApplicationDetailService,
        Depends(get_application_detail_service),
    ],
    status: Annotated[ApplicationStatus | None, Query()] = None,
    source: Annotated[ApplicationSource | None, Query()] = None,
    sponsorship: Annotated[SponsorshipStatus | None, Query()] = None,
    first_seen_from: Annotated[datetime | None, Query()] = None,
    first_seen_to: Annotated[datetime | None, Query()] = None,
    role: Annotated[str | None, Query(min_length=1)] = None,
    salary_min: Annotated[int | None, Query(ge=0)] = None,
    salary_max: Annotated[int | None, Query(ge=0)] = None,
    work_mode: Annotated[WorkMode | None, Query()] = None,
) -> list[ApplicationRecord]:
    try:
        return service.list_applications(
            status=status,
            source=source,
            sponsorship=sponsorship,
            first_seen_from=first_seen_from,
            first_seen_to=first_seen_to,
            role=role,
            salary_min=salary_min,
            salary_max=salary_max,
            work_mode=work_mode,
        )
    except ApplicationFilterValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details=(
                ApiErrorDetail(
                    field=f"query.{error.field}",
                    message=error.message,
                    type=error.error_type,
                ),
            ),
        ) from error


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
    except ApplicationReadNotFoundError as error:
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
    except ApplicationReadNotFoundError as error:
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
    "/{application_id}/split",
    response_model=ApplicationSplitResponse,
    summary="Split Application",
    description=(
        "Splits selected events out of an incorrectly grouped application into a "
        "deterministic manually locked application, locks the source application, "
        "recalculates timeline dates, derives target status from moved events, and "
        "records an audited manual correction."
    ),
    responses={
        404: {"model": ApiErrorResponse, "description": "Application not found."},
        409: {"model": ApiErrorResponse, "description": "Application split conflict."},
        422: {"model": ApiErrorResponse, "description": "Request validation failed."},
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
