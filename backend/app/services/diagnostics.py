from __future__ import annotations

from collections.abc import Sequence

from app.db.repositories.metrics import MetricsRepository
from app.models.diagnostics import DiagnosticSegmentComparison, MetricsDiagnosticsResponse
from app.models.metrics import MetricBreakdownRow, MetricsBreakdownDimension, MetricsFilter

DEFAULT_DIAGNOSTIC_DIMENSIONS: tuple[MetricsBreakdownDimension, ...] = (
    "role",
    "source",
    "salary",
    "tech",
    "sponsorship",
    "seniority",
    "work_mode",
)


class DiagnosticsService:
    """Build deterministic diagnostic comparisons from local metrics rows."""

    def __init__(
        self,
        *,
        metrics_repository: MetricsRepository,
        highlight_limit: int = 3,
    ) -> None:
        if highlight_limit < 0:
            msg = "highlight_limit must be greater than or equal to 0"
            raise ValueError(msg)
        self._metrics_repository = metrics_repository
        self._highlight_limit = highlight_limit

    def get_diagnostics(
        self,
        *,
        dimensions: Sequence[MetricsBreakdownDimension] = DEFAULT_DIAGNOSTIC_DIMENSIONS,
        filters: MetricsFilter | None = None,
    ) -> MetricsDiagnosticsResponse:
        response_silence = self._metrics_repository.get_response_silence_metric(
            filters=filters,
        )
        baseline_response_rate = _rate(
            numerator=response_silence.human_response_count,
            denominator=response_silence.total_applications,
        )
        baseline_success_count = self._metrics_repository.count_successful_applications(
            filters=filters,
        )
        baseline_success_rate = _rate(
            numerator=baseline_success_count,
            denominator=response_silence.total_applications,
        )
        baseline_negative_count = self._metrics_repository.count_negative_applications(
            filters=filters,
        )
        baseline_negative_rate = _rate(
            numerator=baseline_negative_count,
            denominator=response_silence.total_applications,
        )
        segments = self._segments_for_dimensions(
            dimensions=dimensions,
            baseline_response_rate=baseline_response_rate,
            baseline_success_rate=baseline_success_rate,
            baseline_negative_rate=baseline_negative_rate,
            filters=filters,
        )

        strongest_response_segments = _strongest_segments(
            segments,
            limit=self._highlight_limit,
        )

        return MetricsDiagnosticsResponse(
            total_applications=response_silence.total_applications,
            baseline_response_count=response_silence.human_response_count,
            baseline_response_rate=baseline_response_rate,
            baseline_success_count=baseline_success_count,
            baseline_success_rate=baseline_success_rate,
            baseline_negative_count=baseline_negative_count,
            baseline_negative_rate=baseline_negative_rate,
            segments=segments,
            strongest_response_correlate=strongest_response_segments[0]
            if strongest_response_segments
            else None,
            strongest_response_segments=strongest_response_segments,
            weakest_response_segments=_weakest_segments(
                segments,
                limit=self._highlight_limit,
            ),
            successful_application_segments=_successful_application_segments(
                segments,
                limit=self._highlight_limit,
            ),
            negative_outcome_segments=_negative_outcome_segments(
                segments,
                limit=self._highlight_limit,
            ),
        )

    def _segments_for_dimensions(
        self,
        *,
        dimensions: Sequence[MetricsBreakdownDimension],
        baseline_response_rate: float | None,
        baseline_success_rate: float | None,
        baseline_negative_rate: float | None,
        filters: MetricsFilter | None,
    ) -> list[DiagnosticSegmentComparison]:
        segments: list[DiagnosticSegmentComparison] = []
        for dimension in dimensions:
            success_counts = self._metrics_repository.get_successful_application_breakdown(
                dimension,
                filters=filters,
            )
            negative_counts = self._metrics_repository.get_negative_application_breakdown(
                dimension,
                filters=filters,
            )
            for row in self._metrics_repository.get_breakdown(dimension, filters=filters):
                segments.append(
                    _diagnostic_segment(
                        row=row,
                        success_count=success_counts.get(row.value, 0),
                        negative_count=negative_counts.get(row.value, 0),
                        baseline_response_rate=baseline_response_rate,
                        baseline_success_rate=baseline_success_rate,
                        baseline_negative_rate=baseline_negative_rate,
                    ),
                )
        return sorted(
            segments,
            key=lambda segment: (
                -(segment.response_rate_lift or 0),
                -segment.application_count,
                segment.dimension,
                segment.value,
            ),
        )


def _diagnostic_segment(
    *,
    row: MetricBreakdownRow,
    success_count: int,
    negative_count: int,
    baseline_response_rate: float | None,
    baseline_success_rate: float | None,
    baseline_negative_rate: float | None,
) -> DiagnosticSegmentComparison:
    response_rate = _rate(
        numerator=row.response_count,
        denominator=row.application_count,
    )
    success_rate = _rate(
        numerator=success_count,
        denominator=row.application_count,
    )
    negative_rate = _rate(
        numerator=negative_count,
        denominator=row.application_count,
    )
    return DiagnosticSegmentComparison(
        dimension=row.dimension,
        value=row.value,
        application_count=row.application_count,
        response_count=row.response_count,
        interview_count=row.interview_count,
        offer_count=row.offer_count,
        success_count=success_count,
        negative_count=negative_count,
        response_rate=response_rate,
        interview_rate=_rate(
            numerator=row.interview_count,
            denominator=row.application_count,
        ),
        offer_rate=_rate(
            numerator=row.offer_count,
            denominator=row.application_count,
        ),
        success_rate=success_rate,
        negative_rate=negative_rate,
        response_rate_lift=None
        if response_rate is None or baseline_response_rate is None
        else response_rate - baseline_response_rate,
        success_rate_lift=None
        if success_rate is None or baseline_success_rate is None
        else success_rate - baseline_success_rate,
        negative_rate_lift=None
        if negative_rate is None or baseline_negative_rate is None
        else negative_rate - baseline_negative_rate,
    )


def _rate(*, numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _strongest_segments(
    segments: Sequence[DiagnosticSegmentComparison],
    *,
    limit: int,
) -> list[DiagnosticSegmentComparison]:
    positive_segments = [
        segment
        for segment in segments
        if segment.response_rate_lift is not None and segment.response_rate_lift > 0
    ]
    return sorted(
        positive_segments,
        key=lambda segment: (
            -float(segment.response_rate_lift or 0),
            -segment.application_count,
            segment.dimension,
            segment.value,
        ),
    )[:limit]


def _weakest_segments(
    segments: Sequence[DiagnosticSegmentComparison],
    *,
    limit: int,
) -> list[DiagnosticSegmentComparison]:
    negative_segments = [
        segment
        for segment in segments
        if segment.response_rate_lift is not None and segment.response_rate_lift < 0
    ]
    return sorted(
        negative_segments,
        key=lambda segment: (
            float(segment.response_rate_lift or 0),
            -segment.application_count,
            segment.dimension,
            segment.value,
        ),
    )[:limit]


def _successful_application_segments(
    segments: Sequence[DiagnosticSegmentComparison],
    *,
    limit: int,
) -> list[DiagnosticSegmentComparison]:
    successful_segments = [
        segment
        for segment in segments
        if segment.success_count > 0
        and segment.success_rate_lift is not None
        and segment.success_rate_lift > 0
    ]
    return sorted(
        successful_segments,
        key=lambda segment: (
            -float(segment.success_rate_lift or 0),
            -segment.success_count,
            -segment.application_count,
            segment.dimension,
            segment.value,
        ),
    )[:limit]


def _negative_outcome_segments(
    segments: Sequence[DiagnosticSegmentComparison],
    *,
    limit: int,
) -> list[DiagnosticSegmentComparison]:
    negative_segments = [
        segment
        for segment in segments
        if segment.negative_count > 0
        and segment.negative_rate_lift is not None
        and segment.negative_rate_lift > 0
    ]
    return sorted(
        negative_segments,
        key=lambda segment: (
            -float(segment.negative_rate_lift or 0),
            -segment.negative_count,
            -segment.application_count,
            segment.dimension,
            segment.value,
        ),
    )[:limit]
