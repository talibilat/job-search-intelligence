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
    """Deterministic summary metrics for the dashboard."""

    distinct_company_count: int = Field(ge=0)
    offers_received: int = Field(ge=0)
    ghosted_applications: int = Field(ge=0)
    rejected_applications: int = Field(
        ge=0,
        description="Total applications whose canonical current status is rejected.",
    )
    ghost_threshold_days: int = Field(ge=1)
    evaluated_at: datetime
    interview_invitation_count: int = Field(ge=0)
