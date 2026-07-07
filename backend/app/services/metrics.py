from __future__ import annotations

from app.db.repositories import ApplicationRepository
from app.models import ResponseSilenceMetric


class MetricsService:
    """Read deterministic dashboard metrics from local SQLite."""

    def __init__(self, application_repository: ApplicationRepository) -> None:
        self._application_repository = application_repository

    def get_response_silence_metric(self) -> ResponseSilenceMetric:
        return self._application_repository.get_response_silence_metric()
