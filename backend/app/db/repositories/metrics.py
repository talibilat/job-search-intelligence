from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from app.db.repositories.base import BaseRepository
from app.models.event import RESPONSE_LIKE_APPLICATION_EVENT_TYPES
from app.models.metrics import (
    MetricBreakdownRow,
    MetricFunnelStage,
    MetricRateName,
    MetricRateRow,
    MetricsBreakdownDimension,
    MetricTimeseriesPoint,
    ResponseSilenceMetric,
)

_RESPONSE_LIKE_EVENT_TYPES = RESPONSE_LIKE_APPLICATION_EVENT_TYPES


class MetricsRepository(BaseRepository[int]):
    """Repository seam for deterministic dashboard metric reads."""

    def count_applications_between(self, *, start_at: str, end_at: str) -> int:
        row = self.execute(
            """
            SELECT COUNT(*)
            FROM applications
            WHERE first_seen_at >= ?
              AND first_seen_at < ?
            """,
            (start_at, end_at),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_distinct_companies(self) -> int:
        row = self.execute(
            """
            SELECT COUNT(DISTINCT LOWER(TRIM(company)))
            FROM applications
            WHERE TRIM(company) != ''
            """,
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_applications_with_offer_events(self) -> int:
        return self._count_applications_with_event("offer")

    def get_rate_metrics(self) -> tuple[MetricRateRow, ...]:
        total_applications = self.count_total_applications()
        response_metric = self.get_response_silence_metric()
        rejected_applications = self.count_rejected_applications()
        ghosted_applications = self._count_applications_with_current_status("ghosted")
        interviewed_applications = self._count_applications_with_event("interview_scheduled")
        offered_applications = self.count_applications_with_offer_events()

        return (
            _rate_metric(
                name="response",
                numerator=response_metric.human_response_count,
                denominator=total_applications,
            ),
            _rate_metric(
                name="rejection",
                numerator=rejected_applications,
                denominator=total_applications,
            ),
            _rate_metric(
                name="ghost",
                numerator=ghosted_applications,
                denominator=total_applications,
            ),
            _rate_metric(
                name="application_to_interview",
                numerator=interviewed_applications,
                denominator=total_applications,
            ),
            _rate_metric(
                name="interview_to_offer",
                numerator=offered_applications,
                denominator=interviewed_applications,
            ),
        )

    def get_funnel_metrics(self) -> tuple[MetricFunnelStage, ...]:
        return (
            MetricFunnelStage(stage="applied", count=self.count_total_applications()),
            MetricFunnelStage(
                stage="response",
                count=self.get_response_silence_metric().human_response_count,
            ),
            MetricFunnelStage(
                stage="assessment",
                count=self._count_applications_with_event("assessment"),
            ),
            MetricFunnelStage(
                stage="interview",
                count=self._count_applications_with_event("interview_scheduled"),
            ),
            MetricFunnelStage(stage="offer", count=self.count_applications_with_offer_events()),
        )

    def get_application_timeseries(self) -> tuple[MetricTimeseriesPoint, ...]:
        rows = self.execute(
            """
            SELECT substr(first_seen_at, 1, 10) AS period_start,
                COUNT(*) AS application_count
            FROM applications
            GROUP BY period_start
            ORDER BY period_start ASC
            """,
        ).fetchall()
        return tuple(
            MetricTimeseriesPoint(
                period_start=str(row["period_start"]),
                application_count=int(row["application_count"]),
            )
            for row in rows
        )

    def get_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
    ) -> tuple[MetricBreakdownRow, ...]:
        if dimension == "tech":
            return self._get_tech_breakdown()
        return self._get_application_breakdown(dimension)

    def get_response_silence_metric(self) -> ResponseSilenceMetric:
        row = self.execute(
            f"""
            SELECT
                COUNT(*) AS total_applications,
                COALESCE(
                    SUM(
                        CASE WHEN EXISTS (
                            SELECT 1
                            FROM application_events
                            WHERE application_events.application_id = applications.id
                              AND application_events.event_type IN ({_response_placeholders()})
                        ) THEN 1 ELSE 0 END
                    ),
                    0
                ) AS human_response_count
            FROM applications
            """,
            _RESPONSE_LIKE_EVENT_TYPES,
        ).fetchone()
        total_applications = int(row["total_applications"] if row is not None else 0)
        human_response_count = int(row["human_response_count"] if row is not None else 0)
        return ResponseSilenceMetric(
            total_applications=total_applications,
            human_response_count=human_response_count,
            silent_count=total_applications - human_response_count,
        )

    def count_total_applications(self) -> int:
        row = self.execute("SELECT COUNT(*) FROM applications").fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_rejected_applications(self) -> int:
        return self._count_applications_with_current_status("rejected")

    def count_interview_invitation_events(self) -> int:
        row = self.execute(
            """
            SELECT COUNT(*)
            FROM application_events
            WHERE event_type = 'interview_scheduled'
            """,
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def _count_applications_with_current_status(self, status: str) -> int:
        return self._fetch_count(
            "SELECT COUNT(*) FROM applications WHERE current_status = ?",
            (status,),
        )

    def _count_applications_with_event(self, event_type: str) -> int:
        return self._fetch_count(
            """
            SELECT COUNT(DISTINCT application_events.application_id)
            FROM application_events
            INNER JOIN applications
                ON applications.id = application_events.application_id
            WHERE application_events.event_type = ?
            """,
            (event_type,),
        )

    def _get_application_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
    ) -> tuple[MetricBreakdownRow, ...]:
        expression = _dimension_expression(dimension)
        rows = self.execute(
            f"""
            SELECT {expression} AS value,
                COUNT(*) AS application_count,
                COALESCE(SUM({_exists_response_case()}), 0) AS response_count,
                COALESCE(SUM({_exists_event_case()}), 0) AS interview_count,
                COALESCE(SUM({_exists_event_case()}), 0) AS offer_count
            FROM applications
            GROUP BY value
            ORDER BY value ASC
            """,
            (*_RESPONSE_LIKE_EVENT_TYPES, "interview_scheduled", "offer"),
        ).fetchall()
        return tuple(_breakdown_row(dimension=dimension, row=row) for row in rows)

    def _get_tech_breakdown(self) -> tuple[MetricBreakdownRow, ...]:
        rows = self.execute(
            f"""
            SELECT LOWER(TRIM(json_each.value)) AS value,
                COUNT(DISTINCT applications.id) AS application_count,
                COALESCE(SUM({_exists_response_case()}), 0) AS response_count,
                COALESCE(SUM({_exists_event_case()}), 0) AS interview_count,
                COALESCE(SUM({_exists_event_case()}), 0) AS offer_count
            FROM applications
            INNER JOIN json_each(applications.tech_stack)
            WHERE TRIM(json_each.value) != ''
            GROUP BY value
            ORDER BY value ASC
            """,
            (*_RESPONSE_LIKE_EVENT_TYPES, "interview_scheduled", "offer"),
        ).fetchall()
        return tuple(_breakdown_row(dimension="tech", row=row) for row in rows)

    def _fetch_count(self, sql: str, parameters: Sequence[object] = ()) -> int:
        row = self.execute(sql, parameters).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_threshold_ghosted_applications(self, *, cutoff_at: str) -> int:
        row = self.execute(
            f"""
            WITH event_order AS (
                SELECT
                    application_events.application_id,
                    application_events.id,
                    application_events.event_type,
                    application_events.event_at,
                    COALESCE(raw_emails.sent_at, application_events.event_at) AS email_sent_at,
                    COALESCE(
                        email_classifications.classified_at,
                        COALESCE(raw_emails.sent_at, application_events.event_at)
                    ) AS classified_at
                FROM application_events
                LEFT JOIN raw_emails
                    ON raw_emails.id = application_events.email_id
                LEFT JOIN email_classifications
                    ON email_classifications.email_id = application_events.email_id
                WHERE application_events.event_type != 'ghost_inferred'
            ),
            latest_applied AS (
                SELECT event_order.*
                FROM event_order
                WHERE event_order.event_type = 'applied'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM event_order AS newer_applied
                    WHERE newer_applied.application_id = event_order.application_id
                      AND newer_applied.event_type = 'applied'
                      AND (
                        newer_applied.event_at > event_order.event_at
                        OR (
                            newer_applied.event_at = event_order.event_at
                            AND newer_applied.email_sent_at > event_order.email_sent_at
                        )
                        OR (
                            newer_applied.event_at = event_order.event_at
                            AND newer_applied.email_sent_at = event_order.email_sent_at
                            AND newer_applied.classified_at > event_order.classified_at
                        )
                        OR (
                            newer_applied.event_at = event_order.event_at
                            AND newer_applied.email_sent_at = event_order.email_sent_at
                            AND newer_applied.classified_at = event_order.classified_at
                            AND newer_applied.id > event_order.id
                        )
                      )
                  )
            ),
            latest_non_ghost AS (
                SELECT event_order.*
                FROM event_order
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM event_order AS newer_event
                    WHERE newer_event.application_id = event_order.application_id
                      AND (
                        newer_event.event_at > event_order.event_at
                        OR (
                            newer_event.event_at = event_order.event_at
                            AND newer_event.email_sent_at > event_order.email_sent_at
                        )
                        OR (
                            newer_event.event_at = event_order.event_at
                            AND newer_event.email_sent_at = event_order.email_sent_at
                            AND newer_event.classified_at > event_order.classified_at
                        )
                        OR (
                            newer_event.event_at = event_order.event_at
                            AND newer_event.email_sent_at = event_order.email_sent_at
                            AND newer_event.classified_at = event_order.classified_at
                            AND newer_event.id > event_order.id
                        )
                      )
                )
            )
            SELECT COUNT(DISTINCT applications.id)
            FROM applications
            INNER JOIN latest_applied
                ON latest_applied.application_id = applications.id
            INNER JOIN latest_non_ghost
                ON latest_non_ghost.application_id = applications.id
            WHERE latest_non_ghost.event_at <= ?
              AND NOT EXISTS (
                SELECT 1
                FROM event_order AS response_event
                WHERE response_event.application_id = applications.id
                  AND response_event.event_type IN ({_response_placeholders()})
                  AND (
                    response_event.event_at > latest_applied.event_at
                    OR (
                        response_event.event_at = latest_applied.event_at
                        AND response_event.email_sent_at > latest_applied.email_sent_at
                    )
                    OR (
                        response_event.event_at = latest_applied.event_at
                        AND response_event.email_sent_at = latest_applied.email_sent_at
                        AND response_event.classified_at > latest_applied.classified_at
                    )
                    OR (
                        response_event.event_at = latest_applied.event_at
                        AND response_event.email_sent_at = latest_applied.email_sent_at
                        AND response_event.classified_at = latest_applied.classified_at
                        AND response_event.id > latest_applied.id
                    )
                  )
              )
            """,
            (cutoff_at, *_RESPONSE_LIKE_EVENT_TYPES),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def map_row(self, row: sqlite3.Row) -> int:
        return int(row[0])


def _response_placeholders() -> str:
    return ", ".join("?" for _ in _RESPONSE_LIKE_EVENT_TYPES)


def _rate_metric(*, name: MetricRateName, numerator: int, denominator: int) -> MetricRateRow:
    rate = 0.0 if denominator == 0 else numerator / denominator
    return MetricRateRow(
        name=name,
        numerator=numerator,
        denominator=denominator,
        rate=rate,
    )


def _dimension_expression(dimension: MetricsBreakdownDimension) -> str:
    if dimension == "role":
        return "COALESCE(NULLIF(LOWER(TRIM(role_title)), ''), 'unknown')"
    if dimension == "source":
        return "COALESCE(NULLIF(source, ''), 'unknown')"
    if dimension == "salary":
        return """
        CASE
            WHEN salary_min IS NULL AND salary_max IS NULL THEN 'unknown'
            WHEN COALESCE(salary_max, salary_min) < 100000 THEN 'under_100k'
            WHEN COALESCE(salary_min, salary_max) >= 150000 THEN '150k_plus'
            ELSE '100k_149k'
        END
        """
    if dimension == "sponsorship":
        return "COALESCE(NULLIF(sponsorship, ''), 'unknown')"
    if dimension == "seniority":
        return "COALESCE(NULLIF(LOWER(TRIM(seniority)), ''), 'unknown')"
    if dimension == "work_mode":
        return "COALESCE(NULLIF(work_mode, ''), 'unknown')"
    msg = f"Unsupported breakdown dimension: {dimension}"
    raise ValueError(msg)


def _exists_response_case() -> str:
    return f"""
    CASE WHEN EXISTS (
        SELECT 1
        FROM application_events
        WHERE application_events.application_id = applications.id
          AND application_events.event_type IN ({_response_placeholders()})
    ) THEN 1 ELSE 0 END
    """


def _exists_event_case() -> str:
    return """
    CASE WHEN EXISTS (
        SELECT 1
        FROM application_events
        WHERE application_events.application_id = applications.id
          AND application_events.event_type = ?
    ) THEN 1 ELSE 0 END
    """


def _breakdown_row(
    *,
    dimension: MetricsBreakdownDimension,
    row: sqlite3.Row,
) -> MetricBreakdownRow:
    return MetricBreakdownRow(
        dimension=dimension,
        value=str(row["value"]),
        application_count=int(row["application_count"]),
        response_count=int(row["response_count"]),
        interview_count=int(row["interview_count"]),
        offer_count=int(row["offer_count"]),
    )
