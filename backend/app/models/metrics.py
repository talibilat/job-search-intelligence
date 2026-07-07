from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ResponseSilenceMetric(BaseModel):
    question_id: Literal["Q-04"] = "Q-04"
    total_applications: int = Field(ge=0)
    human_response_count: int = Field(ge=0)
    silent_count: int = Field(ge=0)


class MetricsSummaryResponse(BaseModel):
    ghosted_applications: int = Field(ge=0)
    ghost_threshold_days: int = Field(ge=1)
    evaluated_at: datetime
