from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetricsSummaryResponse(BaseModel):
    ghosted_applications: int = Field(ge=0)
    ghost_threshold_days: int = Field(ge=1)
    evaluated_at: datetime
