from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    "breakdown",
    "live_applications",
]
StructuredQueryScalar = str | int | float | None


class StructuredQueryRequest(BaseModel):
    """Constrained quantitative query request with no raw-SQL surface."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template: StructuredQueryTemplate
    filters: MetricsFilter | None = None
    breakdown_dimension: MetricsBreakdownDimension | None = None

    @model_validator(mode="after")
    def validate_template_parameters(self) -> Self:
        if self.template == "breakdown" and self.breakdown_dimension is None:
            msg = "breakdown_dimension is required for breakdown structured queries"
            raise ValueError(msg)
        if self.template != "breakdown" and self.breakdown_dimension is not None:
            msg = "breakdown_dimension is only accepted for breakdown structured queries"
            raise ValueError(msg)
        return self


class StructuredQueryRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1)
    values: dict[str, StructuredQueryScalar]


class StructuredQueryResult(BaseModel):
    """Grounded deterministic tool output for later chat synthesis."""

    model_config = ConfigDict(frozen=True)

    tool: Literal["structured_query"] = "structured_query"
    template: StructuredQueryTemplate
    rows: tuple[StructuredQueryRow, ...]
    source: Literal["metrics_repository"] = "metrics_repository"


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

        if request.template == "live_applications":
            if self._application_reader is None:
                raise ValueError("application_reader is required for live application queries")
            now = self._clock().astimezone(UTC)
            filters = request.filters or MetricsFilter()
            rows = []
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
                    filters.first_seen_to.isoformat() if filters.first_seen_to is not None else None
                ),
                role=filters.role,
                salary_min=filters.salary_min,
                salary_max=filters.salary_max,
                work_mode=filters.work_mode,
            ):
                if application.current_status not in {
                    "applied",
                    "in_review",
                    "interview",
                }:
                    continue
                days_waiting = max(0, (now - application.last_activity_at.astimezone(UTC)).days)
                rows.append(
                    StructuredQueryRow(
                        label=application.company,
                        values={
                            "application_id": application.id,
                            "company": application.company,
                            "role_title": application.role_title,
                            "current_status": application.current_status,
                            "last_activity_at": application.last_activity_at.isoformat(),
                            "days_waiting": days_waiting,
                            "follow_up_due": days_waiting >= self._follow_up_threshold_days,
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
