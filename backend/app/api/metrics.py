from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from app.api.dependencies import (
    get_metrics_breakdown_service,
    get_metrics_diagnostics_service,
    get_metrics_funnel_service,
    get_metrics_rates_service,
    get_metrics_response_rate_trend_service,
    get_metrics_summary_service,
    get_metrics_timeseries_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.models import (
    MetricsBreakdownDimension,
    MetricsBreakdownResponse,
    MetricsDiagnosticsResponse,
    MetricsFilter,
    MetricsFunnelResponse,
    MetricsRatesResponse,
    MetricsResponseRateTrendResponse,
    MetricsSummaryResponse,
    MetricsTimeseriesResponse,
    ResponseSilenceMetric,
)
from app.models.application import ApplicationSource, ApplicationStatus, SponsorshipStatus, WorkMode
from app.services.diagnostics import DiagnosticsService
from app.services.metrics import (
    MetricsBreakdownService,
    MetricsFunnelService,
    MetricsRatesService,
    MetricsResponseRateTrendService,
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


def get_metrics_filter(
    status: Annotated[ApplicationStatus | None, Query()] = None,
    source: Annotated[ApplicationSource | None, Query()] = None,
    sponsorship: Annotated[SponsorshipStatus | None, Query()] = None,
    first_seen_from: Annotated[datetime | None, Query()] = None,
    first_seen_to: Annotated[datetime | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
    salary_min: Annotated[int | None, Query(ge=0)] = None,
    salary_max: Annotated[int | None, Query(ge=0)] = None,
    work_mode: Annotated[WorkMode | None, Query()] = None,
) -> MetricsFilter:
    try:
        return MetricsFilter(
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
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details=tuple(_metrics_filter_validation_details(error)),
        ) from error


def _metrics_filter_validation_details(error: ValidationError) -> list[ApiErrorDetail]:
    details: list[ApiErrorDetail] = []
    for validation_error in error.errors():
        message = _metrics_filter_error_message(str(validation_error.get("msg", "")))
        field = _metrics_filter_error_field(message)
        loc = validation_error.get("loc", ())
        if field is None and loc:
            field = f"query.{'.'.join(str(part) for part in loc)}"
        details.append(
            ApiErrorDetail(
                field=field or "query",
                message=message or "Invalid metric filter.",
                type=str(validation_error.get("type", "value_error")),
            ),
        )
    return details


def _metrics_filter_error_message(message: str) -> str:
    if message.startswith("Value error, "):
        return message.removeprefix("Value error, ")
    return message


def _metrics_filter_error_field(message: str) -> str | None:
    if message.startswith("salary_min"):
        return "query.salary_min"
    if message.startswith("first_seen_from"):
        return "query.first_seen_from"
    return None


@router.get(
    "/rates",
    response_model=MetricsRatesResponse,
    responses={422: {"model": ApiErrorResponse}},
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
    filters: Annotated[MetricsFilter, Depends(get_metrics_filter)],
) -> MetricsRatesResponse:
    return service.get_rates(filters=filters)


@router.get(
    "/funnel",
    response_model=MetricsFunnelResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Get Metrics Funnel",
    description=(
        "Returns deterministic Q-16 funnel counts for applied, screen, "
        "interview, final, and offer stages from local applications and "
        "application_events data. The final stage is explicitly zero until "
        "final-round evidence is represented in the data model."
    ),
)
def get_metrics_funnel(
    service: Annotated[
        MetricsFunnelService,
        Depends(get_metrics_funnel_service),
    ],
    filters: Annotated[MetricsFilter, Depends(get_metrics_filter)],
) -> MetricsFunnelResponse:
    return service.get_funnel(filters=filters)


@router.get(
    "/timeseries",
    response_model=MetricsTimeseriesResponse,
    responses={422: {"model": ApiErrorResponse}},
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
    filters: Annotated[MetricsFilter, Depends(get_metrics_filter)],
) -> MetricsTimeseriesResponse:
    return service.get_timeseries(filters=filters)


@router.get(
    "/response-rate-trend",
    response_model=MetricsResponseRateTrendResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Get Metrics Response Rate Trend",
    description=(
        "Returns deterministic response-rate trend points from local applications "
        "and application_events data."
    ),
)
def get_metrics_response_rate_trend(
    service: Annotated[
        MetricsResponseRateTrendService,
        Depends(get_metrics_response_rate_trend_service),
    ],
    filters: Annotated[MetricsFilter, Depends(get_metrics_filter)],
) -> MetricsResponseRateTrendResponse:
    return service.get_response_rate_trend(filters=filters)


@router.get(
    "/diagnostics",
    response_model=MetricsDiagnosticsResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Get Metrics Diagnostics",
    description=(
        "Returns deterministic Phase 3.5 diagnostic segment comparisons from "
        "local applications and application_events data."
    ),
)
def get_metrics_diagnostics(
    service: Annotated[
        DiagnosticsService,
        Depends(get_metrics_diagnostics_service),
    ],
    filters: Annotated[MetricsFilter, Depends(get_metrics_filter)],
) -> MetricsDiagnosticsResponse:
    return service.get_diagnostics(filters=filters)


@router.get(
    "/breakdown",
    response_model=MetricsBreakdownResponse,
    responses={422: {"model": ApiErrorResponse}},
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
    filters: Annotated[MetricsFilter, Depends(get_metrics_filter)],
) -> MetricsBreakdownResponse:
    return service.get_breakdown(dimension, filters=filters)
