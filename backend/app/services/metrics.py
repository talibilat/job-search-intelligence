from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.db.repositories.metrics import MetricsRepository
from app.models import MetricsSummaryResponse, ResponseSilenceMetric

type Clock = Callable[[], datetime]


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
            distinct_company_count=self._metrics_repository.count_distinct_companies(),
            ghosted_applications=ghosted_applications,
            rejected_applications=self._metrics_repository.count_rejected_applications(),
            ghost_threshold_days=self._ghost_threshold_days,
            evaluated_at=evaluated_at,
        )

    def get_response_silence_metric(self) -> ResponseSilenceMetric:
        return self._metrics_repository.get_response_silence_metric()


def _utcnow() -> datetime:
    return datetime.now(UTC)
