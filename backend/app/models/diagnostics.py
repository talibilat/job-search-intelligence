from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.metrics import MetricsBreakdownDimension


class DiagnosticSegmentComparison(BaseModel):
    dimension: MetricsBreakdownDimension
    value: str
    application_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    interview_count: int = Field(ge=0)
    offer_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    response_rate: float | None = Field(default=None, ge=0, le=1)
    interview_rate: float | None = Field(default=None, ge=0, le=1)
    offer_rate: float | None = Field(default=None, ge=0, le=1)
    success_rate: float | None = Field(default=None, ge=0, le=1)
    negative_rate: float | None = Field(default=None, ge=0, le=1)
    response_rate_lift: float | None = Field(default=None, ge=-1, le=1)
    success_rate_lift: float | None = Field(default=None, ge=-1, le=1)
    negative_rate_lift: float | None = Field(default=None, ge=-1, le=1)


class MetricsDiagnosticsResponse(BaseModel):
    total_applications: int = Field(ge=0)
    baseline_response_count: int = Field(ge=0)
    baseline_response_rate: float | None = Field(default=None, ge=0, le=1)
    baseline_success_count: int = Field(ge=0)
    baseline_success_rate: float | None = Field(default=None, ge=0, le=1)
    baseline_negative_count: int = Field(ge=0)
    baseline_negative_rate: float | None = Field(default=None, ge=0, le=1)
    segments: list[DiagnosticSegmentComparison]
    strongest_response_correlate: DiagnosticSegmentComparison | None = None
    strongest_response_segments: list[DiagnosticSegmentComparison]
    weakest_response_segments: list[DiagnosticSegmentComparison]
    successful_application_segments: list[DiagnosticSegmentComparison]
    negative_outcome_segments: list[DiagnosticSegmentComparison]
