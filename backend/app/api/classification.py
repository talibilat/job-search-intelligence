from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api.dependencies import (
    get_aggregation_service,
    get_readonly_email_repository,
    get_structured_extraction_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.db.repositories import EmailRepository
from app.models import (
    ClassificationReprocessingPlan,
    ClassificationRunApiRequest,
    ClassificationRunResponse,
)
from app.models.classification import ClassificationPreRunEstimate
from app.services.aggregation import AggregationService
from app.services.classification_estimate import build_classification_pre_run_estimate
from app.services.classification_reprocessing import build_classification_reprocessing_plan
from app.services.structured_extraction import StructuredExtractionService

router = APIRouter(prefix="/classification", tags=["classification"])


def _validation_details(error: ValidationError) -> list[ApiErrorDetail]:
    return [
        ApiErrorDetail(
            field=".".join(str(part) for part in validation_error.get("loc", ())),
            message=str(validation_error.get("msg", "Invalid classification run request.")),
            type=str(validation_error.get("type", "value_error")),
        )
        for validation_error in error.errors()
    ]


async def _validate_classification_run_request_body(request: Request) -> None:
    raw_body = await request.body()
    if not raw_body.strip():
        return

    try:
        ClassificationRunApiRequest.model_validate_json(raw_body)
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Classification run request validation failed.",
            details=_validation_details(error),
        ) from error


@router.get(
    "/estimate",
    response_model=ClassificationPreRunEstimate,
    summary="Estimate Classification Run",
    description=(
        "Returns deterministic candidate counts, token estimates, and cost availability "
        "for a future bulk classification pass without calling an LLM or exposing email content."
    ),
)
async def classification_estimate(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[
        EmailRepository,
        Depends(get_readonly_email_repository),
    ],
) -> ClassificationPreRunEstimate:
    return build_classification_pre_run_estimate(
        settings=settings,
        email_repository=email_repository,
    )


@router.get(
    "/reprocessing-plan",
    response_model=ClassificationReprocessingPlan,
    summary="Plan Classification Reprocessing",
    description=(
        "Returns deterministic prompt/model-version buckets for retained classification "
        "candidates without calling an LLM or exposing email content."
    ),
)
async def classification_reprocessing_plan(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[
        EmailRepository,
        Depends(get_readonly_email_repository),
    ],
) -> ClassificationReprocessingPlan:
    return build_classification_reprocessing_plan(
        settings=settings,
        email_repository=email_repository,
    )


@router.post(
    "/run",
    response_model=ClassificationRunResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Run Classification Batch",
    description=(
        "Classifies retained email candidates through the configured LLM provider, "
        "idempotently stores classification results plus run accounting, and then "
        "aggregates accepted extractions into applications and timeline events."
    ),
)
async def classification_run(
    settings: Annotated[AppSettings, Depends(get_settings)],
    _validated_request_body: Annotated[
        None,
        Depends(_validate_classification_run_request_body),
    ],
    classification_service: Annotated[
        StructuredExtractionService,
        Depends(get_structured_extraction_service),
    ],
    aggregation_service: Annotated[
        AggregationService,
        Depends(get_aggregation_service),
    ],
) -> ClassificationRunResponse:
    result = await classification_service.run_batch()
    aggregation_result = aggregation_service.run(list(result.accepted_results))
    return ClassificationRunResponse(
        run_id=result.run_record.id,
        provider=result.run_record.provider,
        model=result.run_record.model,
        prompt_version=result.run_record.prompt_version,
        started_at=result.run_record.started_at,
        completed_at=result.run_record.completed_at,
        candidate_count=result.run_record.candidate_count,
        classified_count=result.run_record.classified_count,
        malformed_count=len(result.malformed_results),
        prompt_tokens=result.run_record.prompt_tokens,
        completion_tokens=result.run_record.completion_tokens,
        total_tokens=result.run_record.total_tokens,
        estimated_cost_usd=float(result.run_record.estimated_cost_usd),
        classification_mode=settings.classification_mode,
        llm_provider=settings.llm_provider,
        applications_upserted=aggregation_result.applications_upserted,
        events_upserted=aggregation_result.events_upserted,
        skipped_not_job_related=aggregation_result.skipped_not_job_related,
        manual_conflict_count=aggregation_result.manual_conflict_count,
    )
