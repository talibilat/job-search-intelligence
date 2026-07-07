from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_metrics_breakdown_service,
    get_metrics_rates_service,
    get_metrics_summary_service,
    get_metrics_timeseries_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.models import (
    MetricsBreakdownDimension,
    MetricsBreakdownResponse,
    MetricsRatesResponse,
    MetricsSummaryResponse,
    MetricsTimeseriesResponse,
    ResponseSilenceMetric,
)
from app.services.metrics import (
    MetricsBreakdownService,
    MetricsRatesService,
    MetricsSummaryService,
    MetricsTimeseriesService,
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


@router.get(
    "/timeseries",
    response_model=MetricsTimeseriesResponse,
    summary="Get Metrics Timeseries",
    description=(
        "Returns deterministic application-volume timeseries points from local applications data."
    ),
)
def get_metrics_timeseries(
    service: Annotated[
        MetricsTimeseriesService,
        Depends(get_metrics_timeseries_service),
    ],
) -> MetricsTimeseriesResponse:
    return service.get_timeseries()


@router.get(
    "/breakdown",
    response_model=MetricsBreakdownResponse,
    summary="Get Metrics Breakdown",
    description=(
        "Returns deterministic dashboard breakdown rows for a supported dimension "
        "from local applications and application_events data."
    ),
)
def get_metrics_breakdown(
    service: Annotated[
        MetricsBreakdownService,
        Depends(get_metrics_breakdown_service),
    ],
    dimension: Annotated[MetricsBreakdownDimension, Query()],
) -> MetricsBreakdownResponse:
    return service.get_breakdown(dimension)
