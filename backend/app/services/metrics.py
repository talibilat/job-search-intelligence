from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.db.repositories.metrics import MetricsRepository
from app.models import (
    MetricsBreakdownDimension,
    MetricsBreakdownResponse,
    MetricsFilter,
    MetricsFunnelResponse,
    MetricsRatesResponse,
    MetricsResponseRateTrendResponse,
    MetricsSummaryResponse,
    MetricsTimeseriesResponse,
    ResponseSilenceMetric,
)
from app.models.metrics import ApplicationWindowMetric, MetricRate, MetricsApplicationWindow

type Clock = Callable[[], datetime]


class MetricsWindowValidationError(ValueError):
    def __init__(self, *, field: str, message: str, error_type: str) -> None:
        self.field = field
        self.message = message
        self.error_type = error_type
        super().__init__(message)


class MetricsSummaryService:
    """Build deterministic dashboard summary metrics from local SQLite."""

    def __init__(
        self,
        *,
        metrics_repository: MetricsRepository,
        ghost_threshold_days: int,
        clock: Clock | None = None,
    ) -> None:
        self._metrics_repository = metrics_repository
        self._ghost_threshold_days = ghost_threshold_days
        self._clock = clock or _utcnow

    def get_summary(
        self,
        *,
        anchor_at: datetime | None = None,
        custom_start_at: datetime | None = None,
        custom_end_at: datetime | None = None,
        filters: MetricsFilter | None = None,
    ) -> MetricsSummaryResponse:
        evaluated_at = self._clock()
        cutoff_at = evaluated_at - timedelta(days=self._ghost_threshold_days)
        ghosted_applications = self._metrics_repository.count_threshold_ghosted_applications(
            cutoff_at=cutoff_at.isoformat(),
            filters=filters,
        )
        anchor = (
            _datetime_filter_value(anchor_at, "anchor_at")
            if anchor_at is not None
            else evaluated_at.astimezone(UTC)
        )
        return MetricsSummaryResponse(
            total_applications=self._metrics_repository.count_total_applications(filters=filters),
            live_applications=self._metrics_repository.count_live_applications(
                active_after=cutoff_at.isoformat(), filters=filters
            ),
            distinct_company_count=self._metrics_repository.count_distinct_companies(
                filters=filters,
            ),
            offers_received=self._metrics_repository.count_applications_with_offer_events(
                filters=filters,
            ),
            ghosted_applications=ghosted_applications,
            rejected_applications=self._metrics_repository.count_rejected_applications(
                filters=filters,
            ),
            ghost_threshold_days=self._ghost_threshold_days,
            evaluated_at=evaluated_at,
            interview_invitation_count=(
                self._metrics_repository.count_interview_invitation_events(filters=filters)
            ),
            average_time_to_first_response=(
                self._metrics_repository.get_time_to_first_response_metric(filters=filters)
            ),
            average_time_to_rejection=(
                self._metrics_repository.get_time_to_rejection_metric(filters=filters)
            ),
            personal_ghost_threshold=(
                self._metrics_repository.get_personal_ghost_threshold_metric(
                    evaluated_at=evaluated_at.isoformat(),
                    fallback_threshold_days=self._ghost_threshold_days,
                    filters=filters,
                )
            ),
            application_windows=self._application_windows(
                anchor_at=anchor,
                custom_start_at=custom_start_at,
                custom_end_at=custom_end_at,
                filters=filters,
            ),
        )

    def get_response_silence_metric(
        self,
        filters: MetricsFilter | None = None,
    ) -> ResponseSilenceMetric:
        return self._metrics_repository.get_response_silence_metric(filters=filters)

    def _application_windows(
        self,
        *,
        anchor_at: datetime,
        custom_start_at: datetime | None,
        custom_end_at: datetime | None,
        filters: MetricsFilter | None,
    ) -> list[ApplicationWindowMetric]:
        week_start = _week_start(anchor_at)
        month_start = datetime(anchor_at.year, anchor_at.month, 1, tzinfo=UTC)
        year_start = datetime(anchor_at.year, 1, 1, tzinfo=UTC)

        windows = [
            self._application_window(
                window=MetricsApplicationWindow.WEEK,
                start_at=week_start,
                end_at=week_start + timedelta(days=7),
                filters=filters,
            ),
            self._application_window(
                window=MetricsApplicationWindow.MONTH,
                start_at=month_start,
                end_at=_next_month_start(month_start),
                filters=filters,
            ),
            self._application_window(
                window=MetricsApplicationWindow.YEAR,
                start_at=year_start,
                end_at=datetime(anchor_at.year + 1, 1, 1, tzinfo=UTC),
                filters=filters,
            ),
        ]

        if custom_start_at is not None or custom_end_at is not None:
            custom_start, custom_end = _custom_window_values(
                custom_start_at=custom_start_at,
                custom_end_at=custom_end_at,
            )
            windows.append(
                self._application_window(
                    window=MetricsApplicationWindow.CUSTOM,
                    start_at=custom_start,
                    end_at=custom_end,
                    filters=filters,
                ),
            )

        return windows

    def _application_window(
        self,
        *,
        window: MetricsApplicationWindow,
        start_at: datetime,
        end_at: datetime,
        filters: MetricsFilter | None,
    ) -> ApplicationWindowMetric:
        count = self._metrics_repository.count_applications_between(
            start_at=start_at.isoformat(),
            end_at=end_at.isoformat(),
            filters=filters,
        )
        return ApplicationWindowMetric(
            window=window,
            start_at=start_at,
            end_at=end_at,
            application_count=count,
        )


def _datetime_filter_value(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MetricsWindowValidationError(
            field=field,
            message=f"{field} must include a timezone offset.",
            error_type="timezone_aware",
        )
    return value.astimezone(UTC)


def _custom_window_values(
    *,
    custom_start_at: datetime | None,
    custom_end_at: datetime | None,
) -> tuple[datetime, datetime]:
    if custom_start_at is None:
        raise MetricsWindowValidationError(
            field="custom_start_at",
            message="custom_start_at and custom_end_at must be provided together.",
            error_type="missing_custom_window_bound",
        )
    if custom_end_at is None:
        raise MetricsWindowValidationError(
            field="custom_end_at",
            message="custom_start_at and custom_end_at must be provided together.",
            error_type="missing_custom_window_bound",
        )

    start_at = _datetime_filter_value(custom_start_at, "custom_start_at")
    end_at = _datetime_filter_value(custom_end_at, "custom_end_at")
    if start_at >= end_at:
        raise MetricsWindowValidationError(
            field="custom_start_at",
            message="custom_start_at must be earlier than custom_end_at.",
            error_type="value_error",
        )
    return start_at, end_at


def _week_start(anchor_at: datetime) -> datetime:
    day_start = datetime(
        anchor_at.year,
        anchor_at.month,
        anchor_at.day,
        tzinfo=UTC,
    )
    return day_start - timedelta(days=day_start.weekday())


def _next_month_start(month_start: datetime) -> datetime:
    if month_start.month == 12:
        return datetime(month_start.year + 1, 1, 1, tzinfo=UTC)
    return datetime(month_start.year, month_start.month + 1, 1, tzinfo=UTC)


class MetricsRatesService:
    """Build deterministic dashboard rate metrics from local SQLite."""

    def __init__(
        self,
        *,
        metrics_repository: MetricsRepository,
        ghost_threshold_days: int,
        clock: Clock | None = None,
    ) -> None:
        self._metrics_repository = metrics_repository
        self._ghost_threshold_days = ghost_threshold_days
        self._clock = clock or _utcnow

    def get_rates(self, filters: MetricsFilter | None = None) -> MetricsRatesResponse:
        evaluated_at = self._clock()
        cutoff_at = evaluated_at - timedelta(days=self._ghost_threshold_days)
        response_silence = self._metrics_repository.get_response_silence_metric(filters=filters)
        denominator = response_silence.total_applications
        response_numerator = response_silence.human_response_count
        rejection_numerator = self._metrics_repository.count_rejected_applications(filters=filters)
        ghost_numerator = self._metrics_repository.count_threshold_ghosted_applications(
            cutoff_at=cutoff_at.isoformat(),
            filters=filters,
        )
        application_to_interview_numerator = (
            self._metrics_repository.count_applications_with_interview_events(filters=filters)
        )
        interview_to_offer_numerator = (
            self._metrics_repository.count_applications_with_offer_after_interview_events(
                filters=filters,
            )
        )
        return MetricsRatesResponse(
            overall_response_rate=MetricRate(
                numerator=response_numerator,
                denominator=denominator,
                rate=_rate(numerator=response_numerator, denominator=denominator),
            ),
            rejection_rate=MetricRate(
                numerator=rejection_numerator,
                denominator=denominator,
                rate=_rate(numerator=rejection_numerator, denominator=denominator),
            ),
            ghost_rate=MetricRate(
                numerator=ghost_numerator,
                denominator=denominator,
                rate=_rate(numerator=ghost_numerator, denominator=denominator),
            ),
            application_to_interview_rate=MetricRate(
                numerator=application_to_interview_numerator,
                denominator=denominator,
                rate=_rate(
                    numerator=application_to_interview_numerator,
                    denominator=denominator,
                ),
            ),
            interview_to_offer_rate=MetricRate(
                numerator=interview_to_offer_numerator,
                denominator=application_to_interview_numerator,
                rate=_rate(
                    numerator=interview_to_offer_numerator,
                    denominator=application_to_interview_numerator,
                ),
            ),
        )


class MetricsTimeseriesService:
    """Build deterministic dashboard timeseries metrics from local SQLite."""

    def __init__(self, *, metrics_repository: MetricsRepository) -> None:
        self._metrics_repository = metrics_repository

    def get_timeseries(
        self,
        filters: MetricsFilter | None = None,
    ) -> MetricsTimeseriesResponse:
        return MetricsTimeseriesResponse(
            points=list(self._metrics_repository.get_application_timeseries(filters=filters)),
        )


class MetricsFunnelService:
    """Build deterministic dashboard funnel metrics from local SQLite."""

    def __init__(self, *, metrics_repository: MetricsRepository) -> None:
        self._metrics_repository = metrics_repository

    def get_funnel(self, filters: MetricsFilter | None = None) -> MetricsFunnelResponse:
        return MetricsFunnelResponse(
            stages=list(self._metrics_repository.get_funnel_metrics(filters=filters)),
        )


class MetricsResponseRateTrendService:
    """Build deterministic response-rate trend metrics from local SQLite."""

    def __init__(self, *, metrics_repository: MetricsRepository) -> None:
        self._metrics_repository = metrics_repository

    def get_response_rate_trend(
        self,
        filters: MetricsFilter | None = None,
    ) -> MetricsResponseRateTrendResponse:
        return MetricsResponseRateTrendResponse(
            points=list(self._metrics_repository.get_response_rate_timeseries(filters=filters)),
        )


class MetricsBreakdownService:
    """Build deterministic dashboard breakdown metrics from local SQLite."""

    def __init__(self, *, metrics_repository: MetricsRepository) -> None:
        self._metrics_repository = metrics_repository

    def get_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        filters: MetricsFilter | None = None,
    ) -> MetricsBreakdownResponse:
        return MetricsBreakdownResponse(
            dimension=dimension,
            rows=list(self._metrics_repository.get_breakdown(dimension, filters=filters)),
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _rate(*, numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
