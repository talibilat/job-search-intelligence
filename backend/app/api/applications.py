from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError

from app.api.dependencies import (
    get_application_correction_conflict_service,
    get_application_correction_history_service,
    get_application_correction_service,
    get_application_detail_service,
    get_application_events_service,
    get_ghost_inference_service,
    get_manual_edit_service,
    get_manual_merge_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.models import (
    ApplicationCorrectionConflictRecord,
    ApplicationCorrectionRecord,
    ApplicationRecord,
    ApplicationStatusEditRequest,
    ApplicationStatusEditResponse,
    GhostInferenceRunApiRequest,
    GhostInferenceRunResponse,
)
from app.models.application import ApplicationStatusCountsResponse
from app.models.application_edit import ApplicationEventEditRequest, ApplicationEventEditResponse
from app.models.application_merge import ApplicationMergeRequest, ApplicationMergeResponse
from app.models.correction import (
    ApplicationResetLockRequest,
    ApplicationResetLockResponse,
    ApplicationSplitRequest,
    ApplicationSplitResponse,
)
from app.models.records import (
    ApplicationEventTimelineRecord,
    ApplicationSource,
    ApplicationStatus,
    RecentApplicationEventRecord,
    SponsorshipStatus,
    WorkMode,
)
from app.services.application_corrections import (
    ApplicationCorrectionService,
    ApplicationLockResetConflictError,
    ApplicationSplitConflictError,
)
from app.services.application_corrections import (
    ApplicationNotFoundError as ApplicationCorrectionNotFoundError,
)
from app.services.applications import (
    ApplicationCorrectionConflictService,
    ApplicationCorrectionHistoryService,
    ApplicationDetailService,
    ApplicationEventsService,
    ApplicationFilterValidationError,
)
from app.services.applications import (
    ApplicationNotFoundError as ApplicationReadNotFoundError,
)
from app.services.ghost_inference import GhostInferenceService
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


def _validation_details(error: ValidationError) -> list[ApiErrorDetail]:
    return [
        ApiErrorDetail(
            field=".".join(str(part) for part in validation_error.get("loc", ())),
            message=str(validation_error.get("msg", "Invalid application request.")),
            type=str(validation_error.get("type", "value_error")),
        )
        for validation_error in error.errors()
    ]


async def _validate_ghost_inference_request_body(request: Request) -> None:
    raw_body = await request.body()
    if not raw_body.strip():
        return

    try:
        GhostInferenceRunApiRequest.model_validate_json(raw_body)
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Ghost inference request validation failed.",
            details=_validation_details(error),
        ) from error


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


@router.post(
    "/ghost-inference",
    response_model=GhostInferenceRunResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Run Ghost Inference",
    description=(
        "Marks applied applications as ghosted when their event timeline has no "
        "response after the configured silence threshold."
    ),
)
async def run_ghost_inference(
    _validated_body: Annotated[
        None,
        Depends(_validate_ghost_inference_request_body),
    ],
    service: Annotated[
        GhostInferenceService,
        Depends(get_ghost_inference_service),
    ],
) -> GhostInferenceRunResponse:
    return service.run()


@router.get(
    "/status-counts",
    response_model=ApplicationStatusCountsResponse,
    summary="Get Application Status Counts",
    description=(
        "Returns deterministic application counts per canonical current status "
        "from the local SQLite source of truth, zero-filled for unused statuses."
    ),
)
def get_application_status_counts(
    service: Annotated[
        ApplicationDetailService,
        Depends(get_application_detail_service),
    ],
) -> ApplicationStatusCountsResponse:
    return service.get_status_counts()


@router.get(
    "/events/recent",
    response_model=list[RecentApplicationEventRecord],
    summary="List Recent Application Events",
    description=(
        "Returns the newest timeline events across all applications for the "
        "overview activity feed, with source-email subject metadata only."
    ),
)
def list_recent_application_events(
    service: Annotated[
        ApplicationEventsService,
        Depends(get_application_events_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[RecentApplicationEventRecord]:
    return service.list_recent_events(limit=limit)


@router.get(
    "/{id}",
    response_model=ApplicationRecord,
    responses={404: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
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
    response_model=list[ApplicationEventTimelineRecord],
    responses={404: {"model": ApiErrorResponse}},
    summary="List Application Events",
    description=(
        "Returns the canonical event timeline for one application from local SQLite, "
        "enriched with source-email subject metadata and classification confidence."
    ),
)
def get_application_events(
    id: str,
    service: Annotated[
        ApplicationEventsService,
        Depends(get_application_events_service),
    ],
) -> list[ApplicationEventTimelineRecord]:
    try:
        return service.list_application_timeline(id)
    except ApplicationReadNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application not found.",
        ) from error


@router.get(
    "/{id}/correction-conflicts",
    response_model=list[ApplicationCorrectionConflictRecord],
    responses={404: {"model": ApiErrorResponse}},
    summary="List Application Correction Conflicts",
    description=(
        "Returns automatic evidence conflicts recorded for one manually corrected "
        "application without exposing private email body content."
    ),
)
def get_application_correction_conflicts(
    id: str,
    service: Annotated[
        ApplicationCorrectionConflictService,
        Depends(get_application_correction_conflict_service),
    ],
) -> list[ApplicationCorrectionConflictRecord]:
    try:
        return service.list_application_conflicts(id)
    except ApplicationReadNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application not found.",
        ) from error


@router.get(
    "/{id}/corrections",
    response_model=list[ApplicationCorrectionRecord],
    responses={404: {"model": ApiErrorResponse}},
    summary="List Application Correction History",
    description=(
        "Returns the newest-first audit history for one manually corrected application "
        "from local SQLite."
    ),
)
def get_application_correction_history(
    id: str,
    service: Annotated[
        ApplicationCorrectionHistoryService,
        Depends(get_application_correction_history_service),
    ],
) -> list[ApplicationCorrectionRecord]:
    try:
        return service.list_application_corrections(id)
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
    "/{application_id}/reset-lock",
    response_model=ApplicationResetLockResponse,
    summary="Reset Application Correction Lock",
    description=(
        "Clears one application's manual correction lock so future automatic "
        "aggregation can update the application summary again, and records an "
        "audited reset_lock correction."
    ),
    responses={
        404: {"model": ApiErrorResponse, "description": "Application not found."},
        409: {"model": ApiErrorResponse, "description": "Application lock reset conflict."},
        422: {"model": ApiErrorResponse, "description": "Request validation failed."},
    },
)
async def reset_application_lock(
    application_id: str,
    request: ApplicationResetLockRequest,
    correction_service: Annotated[
        ApplicationCorrectionService,
        Depends(get_application_correction_service),
    ],
) -> ApplicationResetLockResponse:
    try:
        return correction_service.reset_application_lock(
            application_id=application_id,
            reason=request.reason,
        )
    except ApplicationCorrectionNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message=error.public_message,
        ) from error
    except ApplicationLockResetConflictError as error:
        raise ApiError(
            status_code=409,
            code=ApiErrorCode.CONFLICT,
            message=error.public_message,
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
    except ApplicationCorrectionNotFoundError as error:
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
