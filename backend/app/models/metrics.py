from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.application import ApplicationStatus


class MetricsSummaryResponse(BaseModel):
    ghosted_applications: int = Field(ge=0)
    ghost_threshold_days: int = Field(ge=1)
    evaluated_at: datetime


class MetricStatusCount(BaseModel):
    status: ApplicationStatus
    count: int = Field(ge=0)


class FoundationalMetricsSnapshot(BaseModel):
    total_applications: int = Field(ge=0)
    distinct_companies: int = Field(ge=0)
    status_counts: tuple[MetricStatusCount, ...]
    generated_at: datetime
