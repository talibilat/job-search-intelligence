from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.repositories import MetricsRepository
from app.models import MetricsFilter
from app.models.application import (
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from app.models.metrics import MetricsBreakdownDimension
from app.models.records import ApplicationRecord
from app.services.diagnostics import DiagnosticsService

StructuredQueryTemplate = Literal[
    "total_applications",
    "summary_counts",
    "rates",
    "funnel",
    "timing",
    "personal_ghost_threshold",
    "application_timeseries",
    "response_rate_timeseries",
    "successful_application_segments",
    "negative_outcome_segments",
    "strongest_response_correlate",
    "wasted_effort_segments",
    "best_roi_source",
    "sponsorship_response_impact",
    "skill_signal_segments",
    "adjacent_role_suggestions",
    "breakdown",
    "live_applications",
    "application_list",
    "company_list",
    "busiest_application_month",
]
StructuredQueryScalar = str | int | float | None
DateWindowKind = Literal[
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
    "rolling_days",
    "calendar_year",
    "custom",
]


class DateWindowSpec(BaseModel):
    """Planner-safe local calendar window, resolved by the tool rather than the LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DateWindowKind
    days: int | None = Field(default=None, ge=1, le=3660)
    year: int | None = Field(default=None, ge=1, le=9998)
    start_date: date | None = None
    end_date_exclusive: date | None = None

    @model_validator(mode="after")
    def validate_kind_parameters(self) -> Self:
        expected_fields: set[str] = set()
        if self.kind == "rolling_days":
            expected_fields = {"days"}
        elif self.kind == "calendar_year":
            expected_fields = {"year"}
        elif self.kind == "custom":
            expected_fields = {"start_date", "end_date_exclusive"}

        values = {
            "days": self.days,
            "year": self.year,
            "start_date": self.start_date,
            "end_date_exclusive": self.end_date_exclusive,
        }
        supplied_fields = {name for name, value in values.items() if value is not None}
        if supplied_fields != expected_fields:
            msg = f"{self.kind} date window requires exactly {sorted(expected_fields)}"
            raise ValueError(msg)
        if (
            self.kind == "custom"
            and self.start_date is not None
            and self.end_date_exclusive is not None
            and self.start_date >= self.end_date_exclusive
        ):
            msg = "start_date must be before end_date_exclusive"
            raise ValueError(msg)
        return self


class ResolvedDateWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: DateWindowKind
    timezone: str
    start_at: datetime
    end_at: datetime


class StructuredQueryRequest(BaseModel):
    """Constrained quantitative query request with no raw-SQL surface."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template: StructuredQueryTemplate
    filters: MetricsFilter | None = None
    breakdown_dimension: MetricsBreakdownDimension | None = None
    date_window: DateWindowSpec | None = None
    timezone: str = "UTC"
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            msg = "timezone must be a valid IANA timezone name"
            raise ValueError(msg) from error
        return value

    @model_validator(mode="after")
    def validate_template_parameters(self) -> Self:
        if self.template == "breakdown" and self.breakdown_dimension is None:
            msg = "breakdown_dimension is required for breakdown structured queries"
            raise ValueError(msg)
        if self.template != "breakdown" and self.breakdown_dimension is not None:
            msg = "breakdown_dimension is only accepted for breakdown structured queries"
            raise ValueError(msg)
        if self.date_window is not None and self.template not in {
            "total_applications",
            "summary_counts",
            "application_list",
            "company_list",
            "busiest_application_month",
        }:
            msg = "date_window is not accepted for this structured query template"
            raise ValueError(msg)
        return self


class StructuredQueryRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1)
    values: dict[str, StructuredQueryScalar | tuple[str, ...]]


class StructuredQueryResult(BaseModel):
    """Grounded deterministic tool output for later chat synthesis."""

    model_config = ConfigDict(frozen=True)

    tool: Literal["structured_query"] = "structured_query"
    template: StructuredQueryTemplate
    rows: tuple[StructuredQueryRow, ...]
    source: Literal["metrics_repository"] = "metrics_repository"
    resolved_date_window: ResolvedDateWindow | None = None
    total_matching_count: int | None = Field(default=None, ge=0)
    returned_count: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=1, le=100)
    truncated: bool | None = None


class StructuredQueryTool:
    """Run whitelisted deterministic metric templates for quantitative chat questions."""

    def __init__(
        self,
        *,
        metrics_repository: MetricsRepository,
        ghost_threshold_days: int,
        follow_up_threshold_days: int = 7,
        application_reader: LiveApplicationReader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ghost_threshold_days < 1:
            msg = "ghost_threshold_days must be at least 1"
            raise ValueError(msg)
        if follow_up_threshold_days < 1:
            msg = "follow_up_threshold_days must be at least 1"
            raise ValueError(msg)
        self._metrics_repository = metrics_repository
        self._ghost_threshold_days = ghost_threshold_days
        self._follow_up_threshold_days = follow_up_threshold_days
        self._application_reader = application_reader
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self, request: StructuredQueryRequest) -> StructuredQueryResult:
        resolved_window = self._resolve_date_window(request)
        if resolved_window is not None:
            request = request.model_copy(
                update={
                    "filters": _compose_date_window_filter(
                        request.filters,
                        resolved_window=resolved_window,
                    )
                }
            )

        if request.template == "application_list":
            limit = request.limit
            application_metric_rows = self._metrics_repository.list_applications(
                filters=request.filters,
                limit=limit,
            )
            total_matching_count = self._metrics_repository.count_total_applications(
                filters=request.filters
            )
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=row.application_id,
                        values={
                            "application_id": row.application_id,
                            "company": row.company,
                            "role_title": row.role_title,
                            "status": row.status,
                            "first_seen_at": row.first_seen_at.isoformat(),
                            "last_activity_at": row.last_activity_at.isoformat(),
                        },
                    )
                    for row in application_metric_rows
                ),
                resolved_date_window=resolved_window,
                total_matching_count=total_matching_count,
                returned_count=len(application_metric_rows),
                limit=limit,
                truncated=len(application_metric_rows) < total_matching_count,
            )

        if request.template == "company_list":
            limit = request.limit
            company_metric_rows = self._metrics_repository.list_companies(
                filters=request.filters,
                limit=limit,
            )
            total_matching_count = self._metrics_repository.count_distinct_companies(
                filters=request.filters
            )
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=row.company,
                        values={
                            "company": row.company,
                            "application_count": row.application_count,
                            "role_titles": row.role_titles,
                            "application_ids": row.application_ids,
                        },
                    )
                    for row in company_metric_rows
                ),
                resolved_date_window=resolved_window,
                total_matching_count=total_matching_count,
                returned_count=len(company_metric_rows),
                limit=limit,
                truncated=len(company_metric_rows) < total_matching_count,
            )

        if request.template == "busiest_application_month":
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=row.month_start,
                        values={
                            "month_start": row.month_start,
                            "application_count": row.application_count,
                        },
                    )
                    for row in self._metrics_repository.get_busiest_application_months(
                        timezone=request.timezone,
                        filters=request.filters,
                    )
                ),
                resolved_date_window=resolved_window,
            )

        if request.template == "total_applications":
            return StructuredQueryResult(
                template=request.template,
                rows=(
                    StructuredQueryRow(
                        label="total_applications",
                        values={
                            "application_count": self._metrics_repository.count_total_applications(
                                filters=request.filters,
                            ),
                        },
                    ),
                ),
                resolved_date_window=resolved_window,
            )

        if request.template == "summary_counts":
            ghost_cutoff_at = self._ghost_cutoff_at()
            response_silence = self._metrics_repository.get_response_silence_metric(
                filters=request.filters,
            )
            total_applications = self._metrics_repository.count_total_applications(
                filters=request.filters,
            )
            distinct_company_count = self._metrics_repository.count_distinct_companies(
                filters=request.filters,
            )
            offers_received = self._metrics_repository.count_applications_with_offer_events(
                filters=request.filters,
            )
            ghosted_applications = self._metrics_repository.count_threshold_ghosted_applications(
                cutoff_at=ghost_cutoff_at.isoformat(),
                filters=request.filters,
            )
            rejected_applications = self._metrics_repository.count_rejected_applications(
                filters=request.filters,
            )
            interview_invitation_count = self._metrics_repository.count_interview_invitation_events(
                filters=request.filters,
            )
            return StructuredQueryResult(
                template=request.template,
                rows=(
                    StructuredQueryRow(
                        label="summary_counts",
                        values={
                            "total_applications": total_applications,
                            "distinct_company_count": distinct_company_count,
                            "offers_received": offers_received,
                            "ghosted_applications": ghosted_applications,
                            "rejected_applications": rejected_applications,
                            "interview_invitation_count": interview_invitation_count,
                            "human_response_count": response_silence.human_response_count,
                            "silent_count": response_silence.silent_count,
                        },
                    ),
                ),
                resolved_date_window=resolved_window,
            )

        if request.template == "rates":
            ghost_cutoff_at = self._ghost_cutoff_at()
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=rate.name,
                        values={
                            "numerator": rate.numerator,
                            "denominator": rate.denominator,
                            "rate": rate.rate,
                        },
                    )
                    for rate in self._metrics_repository.get_rate_metrics(
                        ghost_cutoff_at=ghost_cutoff_at.isoformat(),
                        filters=request.filters,
                    )
                ),
            )

        if request.template == "funnel":
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(label=stage.stage, values={"count": stage.count})
                    for stage in self._metrics_repository.get_funnel_metrics(
                        filters=request.filters
                    )
                ),
            )

        if request.template == "timing":
            first_response = self._metrics_repository.get_time_to_first_response_metric(
                filters=request.filters
            )
            rejection = self._metrics_repository.get_time_to_rejection_metric(
                filters=request.filters
            )
            return StructuredQueryResult(
                template=request.template,
                rows=(
                    StructuredQueryRow(
                        label="time_to_first_response",
                        values={
                            "application_count": first_response.application_count,
                            "average_hours": first_response.average_hours,
                        },
                    ),
                    StructuredQueryRow(
                        label="time_to_rejection",
                        values={
                            "application_count": rejection.application_count,
                            "average_hours": rejection.average_hours,
                        },
                    ),
                ),
            )

        if request.template == "personal_ghost_threshold":
            threshold = self._metrics_repository.get_personal_ghost_threshold_metric(
                evaluated_at=self._clock().astimezone(UTC).isoformat(),
                fallback_threshold_days=self._ghost_threshold_days,
                filters=request.filters,
            )
            return StructuredQueryResult(
                template=request.template,
                rows=(
                    StructuredQueryRow(
                        label="personal_ghost_threshold",
                        values={
                            "threshold_days": threshold.threshold_days,
                            "threshold_source": threshold.threshold_source,
                            "response_sample_size": threshold.response_sample_size,
                            "silent_application_count": threshold.silent_application_count,
                        },
                    ),
                ),
            )

        if request.template == "application_timeseries":
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=point.period_start,
                        values={
                            "period_start": point.period_start,
                            "application_count": point.application_count,
                        },
                    )
                    for point in self._metrics_repository.get_application_timeseries(
                        filters=request.filters
                    )
                ),
            )

        if request.template == "response_rate_timeseries":
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=point.period_start,
                        values={
                            "period_start": point.period_start,
                            "response_count": point.response_count,
                            "application_count": point.application_count,
                            "response_rate": point.response_rate,
                        },
                    )
                    for point in self._metrics_repository.get_response_rate_timeseries(
                        filters=request.filters
                    )
                ),
            )

        if request.template == "successful_application_segments":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=f"{segment.dimension}:{segment.value}",
                        values={
                            "dimension": segment.dimension,
                            "value": segment.value,
                            "application_count": segment.application_count,
                            "interview_count": segment.interview_count,
                            "offer_count": segment.offer_count,
                            "success_count": segment.success_count,
                            "success_rate": segment.success_rate,
                            "success_rate_lift": segment.success_rate_lift,
                            "baseline_success_count": diagnostics.baseline_success_count,
                            "baseline_success_rate": diagnostics.baseline_success_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    )
                    for segment in diagnostics.successful_application_segments
                ),
            )

        if request.template == "negative_outcome_segments":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=f"{segment.dimension}:{segment.value}",
                        values={
                            "dimension": segment.dimension,
                            "value": segment.value,
                            "application_count": segment.application_count,
                            "negative_count": segment.negative_count,
                            "negative_rate": segment.negative_rate,
                            "negative_rate_lift": segment.negative_rate_lift,
                            "baseline_negative_count": diagnostics.baseline_negative_count,
                            "baseline_negative_rate": diagnostics.baseline_negative_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    )
                    for segment in diagnostics.negative_outcome_segments
                ),
            )

        if request.template == "strongest_response_correlate":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            segment = diagnostics.strongest_response_correlate
            correlate_rows: tuple[StructuredQueryRow, ...] = ()
            if segment is not None:
                correlate_rows = (
                    StructuredQueryRow(
                        label=f"{segment.dimension}:{segment.value}",
                        values={
                            "dimension": segment.dimension,
                            "value": segment.value,
                            "application_count": segment.application_count,
                            "response_count": segment.response_count,
                            "response_rate": segment.response_rate,
                            "response_rate_lift": segment.response_rate_lift,
                            "baseline_response_count": diagnostics.baseline_response_count,
                            "baseline_response_rate": diagnostics.baseline_response_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    ),
                )
            return StructuredQueryResult(template=request.template, rows=correlate_rows)

        if request.template == "wasted_effort_segments":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=f"{segment.dimension}:{segment.value}",
                        values={
                            "dimension": segment.dimension,
                            "value": segment.value,
                            "application_count": segment.application_count,
                            "response_count": segment.response_count,
                            "response_rate": segment.response_rate,
                            "response_rate_lift": segment.response_rate_lift,
                            "baseline_response_count": diagnostics.baseline_response_count,
                            "baseline_response_rate": diagnostics.baseline_response_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    )
                    for segment in diagnostics.wasted_effort_segments
                ),
            )

        if request.template == "best_roi_source":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            segment = diagnostics.best_roi_source
            roi_rows: tuple[StructuredQueryRow, ...] = ()
            if segment is not None:
                roi_rows = (
                    StructuredQueryRow(
                        label=f"source:{segment.value}",
                        values={
                            "source": segment.value,
                            "application_count": segment.application_count,
                            "interview_count": segment.interview_count,
                            "interview_rate": segment.interview_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    ),
                )
            return StructuredQueryResult(template=request.template, rows=roi_rows)

        if request.template == "sponsorship_response_impact":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            segment = diagnostics.sponsorship_response_impact
            impact_rows: tuple[StructuredQueryRow, ...] = ()
            if segment is not None:
                impact_rows = (
                    StructuredQueryRow(
                        label=f"sponsorship:{segment.value}",
                        values={
                            "sponsorship": segment.value,
                            "application_count": segment.application_count,
                            "response_count": segment.response_count,
                            "response_rate": segment.response_rate,
                            "response_rate_lift": segment.response_rate_lift,
                            "baseline_response_count": diagnostics.baseline_response_count,
                            "baseline_response_rate": diagnostics.baseline_response_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    ),
                )
            return StructuredQueryResult(template=request.template, rows=impact_rows)

        if request.template == "skill_signal_segments":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=f"{signal}:{segment.value}",
                        values={
                            "signal": signal,
                            "skill": segment.value,
                            "application_count": segment.application_count,
                            "response_count": segment.response_count,
                            "response_rate": segment.response_rate,
                            "response_rate_lift": segment.response_rate_lift,
                            "interview_count": segment.interview_count,
                            "interview_rate": segment.interview_rate,
                            "baseline_response_rate": diagnostics.baseline_response_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    )
                    for signal, segments in (
                        ("selling", diagnostics.selling_skill_segments),
                        ("dead_weight", diagnostics.dead_weight_skill_segments),
                    )
                    for segment in segments
                ),
            )

        if request.template == "adjacent_role_suggestions":
            diagnostics = DiagnosticsService(
                metrics_repository=self._metrics_repository
            ).get_diagnostics(filters=request.filters)
            return StructuredQueryResult(
                template=request.template,
                rows=tuple(
                    StructuredQueryRow(
                        label=f"role:{segment.value}",
                        values={
                            "role": segment.value,
                            "application_count": segment.application_count,
                            "interview_count": segment.interview_count,
                            "offer_count": segment.offer_count,
                            "success_count": segment.success_count,
                            "success_rate": segment.success_rate,
                            "total_applications": diagnostics.total_applications,
                        },
                    )
                    for segment in diagnostics.adjacent_role_suggestions
                ),
            )

        if request.template == "live_applications":
            if self._application_reader is None:
                raise ValueError("application_reader is required for live application queries")
            now = self._clock().astimezone(UTC)
            filters = request.filters or MetricsFilter()
            rows = []
            applications = [
                application
                for application in self._application_reader.list_applications(
                    current_status=filters.status,
                    source=filters.source,
                    sponsorship=filters.sponsorship,
                    first_seen_from=(
                        filters.first_seen_from.isoformat()
                        if filters.first_seen_from is not None
                        else None
                    ),
                    first_seen_to=(
                        filters.first_seen_to.isoformat()
                        if filters.first_seen_to is not None
                        else None
                    ),
                    role=filters.role,
                    salary_min=filters.salary_min,
                    salary_max=filters.salary_max,
                    work_mode=filters.work_mode,
                )
                if application.current_status
                in {
                    "applied",
                    "in_review",
                    "interview",
                }
            ]
            batch_reader = getattr(self._application_reader, "list_follow_up_states", None)
            follow_up_states = (
                batch_reader([item.id for item in applications], now=now.isoformat())
                if batch_reader is not None
                else {}
            )
            for application in applications:
                follow_up_state = follow_up_states.get(application.id)
                follow_up_reader = getattr(self._application_reader, "get_follow_up_state", None)
                follow_up_state = follow_up_state or (
                    follow_up_reader(application.id, now=now.isoformat())
                    if batch_reader is None and follow_up_reader is not None
                    else None
                )
                if follow_up_state is not None and follow_up_state.has_future_interview:
                    continue
                latest_at = (
                    follow_up_state.latest_event_at
                    if follow_up_state is not None
                    else application.last_activity_at
                )
                days_waiting = max(0, (now - latest_at.astimezone(UTC)).days)
                waiting_on_employer = follow_up_state is None or (
                    follow_up_state.latest_direction != "inbound"
                    or follow_up_state.latest_event_type == "applied"
                )
                rows.append(
                    StructuredQueryRow(
                        label=application.company.strip() or "Unknown company",
                        values={
                            "application_id": application.id,
                            "company": application.company.strip() or "Unknown company",
                            "role_title": application.role_title,
                            "current_status": application.current_status,
                            "last_activity_at": application.last_activity_at.isoformat(),
                            "days_waiting": days_waiting,
                            "waiting_on_employer": waiting_on_employer,
                            "latest_direction": (
                                follow_up_state.latest_direction
                                if follow_up_state is not None
                                else "unknown"
                            ),
                            "follow_up_due": (
                                waiting_on_employer
                                and days_waiting >= self._follow_up_threshold_days
                            ),
                            "follow_up_threshold_days": self._follow_up_threshold_days,
                        },
                    )
                )
            return StructuredQueryResult(template=request.template, rows=tuple(rows))

        dimension = request.breakdown_dimension
        if dimension is None:
            raise ValueError("breakdown_dimension is required for breakdown structured queries")
        return StructuredQueryResult(
            template=request.template,
            rows=tuple(
                StructuredQueryRow(
                    label=row.value,
                    values={
                        "dimension": row.dimension,
                        "application_count": row.application_count,
                        "response_count": row.response_count,
                        "response_rate": row.response_rate,
                        "interview_count": row.interview_count,
                        "interview_rate": row.interview_rate,
                        "offer_count": row.offer_count,
                        "offer_rate": row.offer_rate,
                    },
                )
                for row in self._metrics_repository.get_breakdown(
                    dimension, filters=request.filters
                )
            ),
        )

    def _ghost_cutoff_at(self) -> datetime:
        return self._clock().astimezone(UTC) - timedelta(days=self._ghost_threshold_days)

    def _resolve_date_window(
        self,
        request: StructuredQueryRequest,
    ) -> ResolvedDateWindow | None:
        spec = request.date_window
        if spec is None:
            return None
        timezone = ZoneInfo(request.timezone)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        local_today = now.astimezone(timezone).date()

        if spec.kind in {"this_week", "last_week"}:
            start_date = local_today - timedelta(days=local_today.weekday())
            if spec.kind == "last_week":
                start_date -= timedelta(days=7)
            end_date = start_date + timedelta(days=7)
        elif spec.kind in {"this_month", "last_month"}:
            start_date = local_today.replace(day=1)
            if spec.kind == "last_month":
                start_date = (start_date - timedelta(days=1)).replace(day=1)
            end_date = _next_month(start_date)
        elif spec.kind in {"this_year", "last_year"}:
            year = local_today.year - (1 if spec.kind == "last_year" else 0)
            start_date = date(year, 1, 1)
            end_date = date(year + 1, 1, 1)
        elif spec.kind == "rolling_days":
            assert spec.days is not None
            start_date = local_today - timedelta(days=spec.days - 1)
            end_date = local_today + timedelta(days=1)
        elif spec.kind == "calendar_year":
            assert spec.year is not None
            start_date = date(spec.year, 1, 1)
            end_date = date(spec.year + 1, 1, 1)
        else:
            assert spec.start_date is not None
            assert spec.end_date_exclusive is not None
            start_date = spec.start_date
            end_date = spec.end_date_exclusive

        return ResolvedDateWindow(
            kind=spec.kind,
            timezone=request.timezone,
            start_at=datetime.combine(start_date, time.min, timezone).astimezone(UTC),
            end_at=datetime.combine(end_date, time.min, timezone).astimezone(UTC),
        )


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _compose_date_window_filter(
    filters: MetricsFilter | None,
    *,
    resolved_window: ResolvedDateWindow,
) -> MetricsFilter:
    filters = filters or MetricsFilter()
    start_at = resolved_window.start_at
    if filters.first_seen_from is not None:
        start_at = max(start_at, filters.first_seen_from)

    # MetricsFilter's legacy upper bound is inclusive, so one microsecond preserves
    # exact [start, end) semantics without widening the public dashboard contract.
    end_at = resolved_window.end_at - timedelta(microseconds=1)
    if filters.first_seen_to is not None:
        end_at = min(end_at, filters.first_seen_to)
    return filters.model_copy(
        update={
            "first_seen_from": start_at,
            "first_seen_to": end_at,
        }
    )


class LiveApplicationReader(Protocol):
    def list_applications(
        self,
        *,
        current_status: ApplicationStatus | None = None,
        source: ApplicationSource | None = None,
        sponsorship: SponsorshipStatus | None = None,
        first_seen_from: str | None = None,
        first_seen_to: str | None = None,
        role: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        work_mode: WorkMode | None = None,
    ) -> list[ApplicationRecord]: ...
