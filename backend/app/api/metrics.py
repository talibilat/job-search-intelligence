from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_metrics_rates_service, get_metrics_summary_service
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.models import MetricsRatesResponse, MetricsSummaryResponse, ResponseSilenceMetric
from app.services.metrics import (
    MetricsRatesService,
    MetricsSummaryService,
    MetricsWindowValidationError,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/response-silence",
    response_model=ResponseSilenceMetric,
    summary="Get Response Versus Silence Metric",
    description=(
        "Answers Q-04 by counting applications with at least one response-like "
        "timeline event versus applications with total silence. Counts are "
        "deterministic SQLite reads from applications and application_events."
    ),
)
def get_response_silence_metric(
    service: Annotated[
        MetricsSummaryService,
        Depends(get_metrics_summary_service),
    ],
) -> ResponseSilenceMetric:
    return service.get_response_silence_metric()


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Get Metrics Summary",
    description=(
        "Returns deterministic dashboard summary metrics and application counts "
        "by date window from the local SQLite source of truth."
    ),
)
def get_metrics_summary(
    service: Annotated[
        MetricsSummaryService,
        Depends(get_metrics_summary_service),
    ],
    anchor_at: Annotated[
        datetime | None,
        Query(description="Timezone-aware instant used to derive this week, month, and year."),
    ] = None,
    custom_start_at: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware custom window start."),
    ] = None,
    custom_end_at: Annotated[
        datetime | None,
        Query(description="Exclusive timezone-aware custom window end."),
    ] = None,
) -> MetricsSummaryResponse:
    try:
        return service.get_summary(
            anchor_at=anchor_at,
            custom_start_at=custom_start_at,
            custom_end_at=custom_end_at,
        )
    except MetricsWindowValidationError as error:
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
    "/rates",
    response_model=MetricsRatesResponse,
    summary="Get Metrics Rates",
    description=(
        "Returns deterministic dashboard rates with explicit numerator and "
        "denominator counts from the local applications source of truth."
    ),
)
def get_metrics_rates(
    service: Annotated[
        MetricsRatesService,
        Depends(get_metrics_rates_service),
    ],
) -> MetricsRatesResponse:
    return service.get_rates()
