from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class MetricRate(BaseModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: float | None = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.numerator > self.denominator:
            msg = "numerator must be less than or equal to denominator"
            raise ValueError(msg)
        return self


class MetricsRatesResponse(BaseModel):
    overall_response_rate: MetricRate


class MetricsApplicationWindow(StrEnum):
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    CUSTOM = "custom"


class ApplicationWindowMetric(BaseModel):
    window: MetricsApplicationWindow
    start_at: datetime
    end_at: datetime
    application_count: int = Field(ge=0)


class ResponseSilenceMetric(BaseModel):
    question_id: Literal["Q-04"] = "Q-04"
    total_applications: int = Field(ge=0)
    human_response_count: int = Field(ge=0)
    silent_count: int = Field(ge=0)


type MetricRateName = Literal[
    "response",
    "rejection",
    "ghost",
    "application_to_interview",
    "interview_to_offer",
]
type MetricFunnelStageName = Literal["applied", "response", "assessment", "interview", "offer"]
type MetricsBreakdownDimension = Literal[
    "role",
    "source",
    "salary",
    "tech",
    "sponsorship",
    "seniority",
    "work_mode",
]


class MetricRateRow(BaseModel):
    name: MetricRateName
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)


class MetricFunnelStage(BaseModel):
    stage: MetricFunnelStageName
    count: int = Field(ge=0)


class MetricTimeseriesPoint(BaseModel):
    period_start: str
    application_count: int = Field(ge=0)


class MetricBreakdownRow(BaseModel):
    dimension: MetricsBreakdownDimension
    value: str
    application_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    interview_count: int = Field(ge=0)
    offer_count: int = Field(ge=0)


class MetricsSummaryResponse(BaseModel):
    """Deterministic summary metrics for the dashboard."""

    total_applications: int = Field(ge=0)
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
    application_windows: list[ApplicationWindowMetric]
