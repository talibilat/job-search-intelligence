from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.models.application import ApplicationSource, ApplicationStatus, SponsorshipStatus, WorkMode


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
    rejection_rate: MetricRate
    ghost_rate: MetricRate


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


class MetricsFilter(BaseModel):
    """Typed dashboard metrics filters for future deterministic metrics queries."""

    status: ApplicationStatus | None = None
    source: ApplicationSource | None = None
    sponsorship: SponsorshipStatus | None = None
    first_seen_from: datetime | None = None
    first_seen_to: datetime | None = None
    role: str | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    work_mode: WorkMode | None = None

    @field_validator("first_seen_from", "first_seen_to")
    @classmethod
    def normalize_datetime(cls, value: datetime | None, info: ValidationInfo) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            msg = f"{info.field_name} must include a timezone offset"
            raise ValueError(msg)
        return value.astimezone(UTC)

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            msg = "role must not be blank"
            raise ValueError(msg)
        return stripped

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if (
            self.first_seen_from is not None
            and self.first_seen_to is not None
            and self.first_seen_from > self.first_seen_to
        ):
            msg = "first_seen_from must be less than or equal to first_seen_to"
            raise ValueError(msg)
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            msg = "salary_min must be less than or equal to salary_max"
            raise ValueError(msg)
        return self


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
    rate: float | None = Field(ge=0, le=1)


class MetricFunnelStage(BaseModel):
    stage: MetricFunnelStageName
    count: int = Field(ge=0)


class MetricTimeseriesPoint(BaseModel):
    period_start: str
    application_count: int = Field(ge=0)


class MetricsTimeseriesResponse(BaseModel):
    points: list[MetricTimeseriesPoint]


class MetricBreakdownRow(BaseModel):
    dimension: MetricsBreakdownDimension
    value: str
    application_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    interview_count: int = Field(ge=0)
    offer_count: int = Field(ge=0)


class MetricsBreakdownResponse(BaseModel):
    dimension: MetricsBreakdownDimension
    rows: list[MetricBreakdownRow]


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
