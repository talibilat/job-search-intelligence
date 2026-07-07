from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_metrics_summary_service
from app.models import MetricsSummaryResponse
from app.services.metrics import MetricsSummaryService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    summary="Get Metrics Summary",
    description=(
        "Returns deterministic dashboard summary metrics from the local SQLite "
        "applications and event timeline source of truth."
    ),
)
def get_metrics_summary(
    service: Annotated[
        MetricsSummaryService,
        Depends(get_metrics_summary_service),
    ],
) -> MetricsSummaryResponse:
    return service.get_summary()
