from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_metrics_service
from app.models import ResponseSilenceMetric
from app.services.metrics import MetricsService

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
    service: Annotated[MetricsService, Depends(get_metrics_service)],
) -> ResponseSilenceMetric:
    return service.get_response_silence_metric()
