from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.db.repositories import ApplicationRepository
from app.db.repositories.metrics import MetricsRepository
from app.models import FoundationalMetricsSnapshot, MetricsSummaryResponse, MetricStatusCount
from app.models.records import ApplicationStatus

type Clock = Callable[[], datetime]

APPLICATION_STATUS_ORDER: tuple[ApplicationStatus, ...] = (
    "applied",
    "in_review",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
)


class MetricsService:
    """Deterministic metrics logic over the canonical applications table."""

    def __init__(
        self,
        application_repository: ApplicationRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._application_repository = application_repository
        self._clock = clock or _utcnow

    def get_foundational_metrics(self) -> FoundationalMetricsSnapshot:
        applications = self._application_repository.list_applications()
        status_counts: dict[ApplicationStatus, int] = dict.fromkeys(
            APPLICATION_STATUS_ORDER,
            0,
        )
        company_keys: set[str] = set()

        for application in applications:
            status_counts[application.current_status] += 1
            company_key = application.company.strip().casefold()
            if company_key:
                company_keys.add(company_key)

        return FoundationalMetricsSnapshot(
            total_applications=len(applications),
            distinct_companies=len(company_keys),
            status_counts=tuple(
                MetricStatusCount(status=status, count=status_counts[status])
                for status in APPLICATION_STATUS_ORDER
            ),
            generated_at=self._clock(),
        )


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

    def get_summary(self) -> MetricsSummaryResponse:
        evaluated_at = self._clock()
        cutoff_at = evaluated_at - timedelta(days=self._ghost_threshold_days)
        ghosted_applications = (
            self._metrics_repository.count_threshold_ghosted_applications(
                cutoff_at=cutoff_at.isoformat(),
            )
        )
        return MetricsSummaryResponse(
            ghosted_applications=ghosted_applications,
            ghost_threshold_days=self._ghost_threshold_days,
            evaluated_at=evaluated_at,
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)
