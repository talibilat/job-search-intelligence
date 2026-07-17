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

StructuredQueryTemplate = Literal[
    "total_applications",
    "summary_counts",
    "rates",
    "funnel",
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
