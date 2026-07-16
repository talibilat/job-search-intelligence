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
    MetricResponseRateTrendPoint,
    MetricsBreakdownDimension,
    MetricsFilter,
    MetricTimeseriesPoint,
    PersonalGhostThresholdMetric,
    ResponseSilenceMetric,
    SilenceAgeBucketMetric,
    SilenceAgeBucketName,
    TimeToFirstResponseMetric,
    TimeToRejectionMetric,
)

_RESPONSE_LIKE_EVENT_TYPES = RESPONSE_LIKE_APPLICATION_EVENT_TYPES


class MetricsRepository(BaseRepository[int]):
    """Repository seam for deterministic dashboard metric reads."""

    def count_applications_between(
        self,
        *,
        start_at: str,
        end_at: str,
        filters: MetricsFilter | None = None,
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        row = self.execute(
            f"""
            SELECT COUNT(*)
            FROM applications
            WHERE first_seen_at >= ?
              AND first_seen_at < ?
              {filter_clause}
            """,
            (start_at, end_at, *filter_parameters),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_distinct_companies(self, filters: MetricsFilter | None = None) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        row = self.execute(
            f"""
            SELECT COUNT(DISTINCT LOWER(TRIM(company)))
            FROM applications
            WHERE TRIM(company) != ''
              {filter_clause}
            """,
            filter_parameters,
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_applications_with_offer_events(
        self,
        filters: MetricsFilter | None = None,
    ) -> int:
        return self._count_applications_with_event("offer", filters=filters)

    def count_successful_applications(self, filters: MetricsFilter | None = None) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        return self._fetch_count(
            f"""
            SELECT COUNT(*)
            FROM applications
            {where_clause}
            {"WHERE" if not where_clause else "AND"} ({_exists_success_case()}) = 1
            """,
            filter_parameters,
        )

    def count_negative_applications(self, filters: MetricsFilter | None = None) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        return self._fetch_count(
            f"""
            SELECT COUNT(*)
            FROM applications
            {where_clause}
            {"WHERE" if not where_clause else "AND"} current_status IN ('rejected', 'ghosted')
            """,
            filter_parameters,
        )

    def get_successful_application_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        filters: MetricsFilter | None = None,
    ) -> dict[str, int]:
        if dimension == "tech":
            return self._get_successful_tech_breakdown(filters=filters)
        return self._get_successful_application_breakdown(dimension, filters=filters)

    def get_negative_application_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        filters: MetricsFilter | None = None,
    ) -> dict[str, int]:
        if dimension == "tech":
            return self._get_negative_tech_breakdown(filters=filters)
        return self._get_negative_application_breakdown(dimension, filters=filters)

    def get_time_to_first_response_metric(
        self,
        filters: MetricsFilter | None = None,
    ) -> TimeToFirstResponseMetric:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        row = self.execute(
            f"""
            WITH first_response AS (
                SELECT
                    applications.id AS application_id,
                    julianday(applications.first_seen_at) AS application_seen_day,
                    MIN(julianday(application_events.event_at)) AS response_day
                FROM applications
                INNER JOIN application_events
                    ON application_events.application_id = applications.id
                WHERE application_events.event_type IN ({_response_placeholders()})
                  AND julianday(application_events.event_at) >= (
                    julianday(applications.first_seen_at)
                  )
                  {filter_clause}
                GROUP BY applications.id
            )
            SELECT
                COUNT(*) AS application_count,
                AVG((response_day - application_seen_day) * 24.0) AS average_hours
            FROM first_response
            """,
            (*_RESPONSE_LIKE_EVENT_TYPES, *filter_parameters),
        ).fetchone()
        if row is None:
            return TimeToFirstResponseMetric(application_count=0, average_hours=None)
        average_hours = row["average_hours"]
        return TimeToFirstResponseMetric(
            application_count=int(row["application_count"]),
            average_hours=None if average_hours is None else round(float(average_hours), 6),
        )

    def get_time_to_rejection_metric(
        self,
        filters: MetricsFilter | None = None,
    ) -> TimeToRejectionMetric:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        row = self.execute(
            f"""
            WITH first_rejection AS (
                SELECT
                    applications.id AS application_id,
                    julianday(applications.first_seen_at) AS application_seen_day,
                    MIN(julianday(application_events.event_at)) AS rejection_day
                FROM applications
                INNER JOIN application_events
                    ON application_events.application_id = applications.id
                WHERE application_events.event_type = 'rejection'
                  AND julianday(application_events.event_at) >= (
                    julianday(applications.first_seen_at)
                  )
                  {filter_clause}
                GROUP BY applications.id
            )
            SELECT
                COUNT(*) AS application_count,
                AVG((rejection_day - application_seen_day) * 24.0) AS average_hours
            FROM first_rejection
            """,
            filter_parameters,
        ).fetchone()
        if row is None:
            return TimeToRejectionMetric(application_count=0, average_hours=None)
        average_hours = row["average_hours"]
        return TimeToRejectionMetric(
            application_count=int(row["application_count"]),
            average_hours=None if average_hours is None else round(float(average_hours), 6),
        )

    def get_personal_ghost_threshold_metric(
        self,
        *,
        evaluated_at: str,
        fallback_threshold_days: int,
        filters: MetricsFilter | None = None,
    ) -> PersonalGhostThresholdMetric:
        response_days = self._first_response_days(filters=filters)

        distribution = _empty_silence_age_distribution()
        for silence_days in self._silent_application_ages(
            evaluated_at=evaluated_at,
            filters=filters,
        ):
            distribution[_silence_age_bucket(silence_days)] += 1

        return PersonalGhostThresholdMetric(
            threshold_days=fallback_threshold_days,
            threshold_source="configured_fallback",
            response_sample_size=len(response_days),
            silent_application_count=sum(distribution.values()),
            silence_age_distribution=[
                SilenceAgeBucketMetric(
                    bucket=bucket,
                    min_days=min_days,
                    max_days=max_days,
                    application_count=distribution[bucket],
                )
                for bucket, min_days, max_days in _SILENCE_AGE_BUCKETS
            ],
        )

    def get_rate_metrics(
        self,
        *,
        ghost_cutoff_at: str,
        filters: MetricsFilter | None = None,
    ) -> tuple[MetricRateRow, ...]:
        total_applications = self.count_total_applications(filters=filters)
        response_metric = self.get_response_silence_metric(filters=filters)
        rejected_applications = self.count_rejected_applications(filters=filters)
        ghosted_applications = self.count_threshold_ghosted_applications(
            cutoff_at=ghost_cutoff_at,
            filters=filters,
        )
        interviewed_applications = self._count_applications_with_event(
            "interview_scheduled",
            filters=filters,
        )
        offered_after_interview_applications = self._count_applications_with_later_event(
            first_event_type="interview_scheduled",
            later_event_type="offer",
            filters=filters,
        )

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
                numerator=offered_after_interview_applications,
                denominator=interviewed_applications,
            ),
        )

    def _first_response_days(self, filters: MetricsFilter | None) -> list[float]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        rows = self.execute(
            f"""
            WITH first_response AS (
                SELECT
                    applications.id AS application_id,
                    julianday(applications.first_seen_at) AS application_seen_day,
                    MIN(julianday(application_events.event_at)) AS response_day
                FROM applications
                INNER JOIN application_events
                    ON application_events.application_id = applications.id
                WHERE application_events.event_type IN ({_response_placeholders()})
                  AND julianday(application_events.event_at) >= (
                    julianday(applications.first_seen_at)
                  )
                  {filter_clause}
                GROUP BY applications.id
            )
            SELECT response_day - application_seen_day AS response_days
            FROM first_response
            ORDER BY response_days ASC
            """,
            (*_RESPONSE_LIKE_EVENT_TYPES, *filter_parameters),
        ).fetchall()
        return [max(0.0, float(row["response_days"])) for row in rows]

    def _silent_application_ages(
        self,
        *,
        evaluated_at: str,
        filters: MetricsFilter | None,
    ) -> list[int]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        prefix = "AND" if where_clause else "WHERE"
        rows = self.execute(
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
                      AND ({_newer_event_predicate("newer_applied", "event_order")})
                  )
            )
            SELECT
                CASE
                    WHEN julianday(?) - julianday(latest_applied.event_at) < 0 THEN 0
                    ELSE CAST(julianday(?) - julianday(latest_applied.event_at) AS INTEGER)
                END AS silence_days
            FROM applications
            INNER JOIN latest_applied
                ON latest_applied.application_id = applications.id
            {where_clause}
            {prefix} applications.current_status != 'withdrawn'
              AND NOT EXISTS (
                SELECT 1
                FROM event_order AS response_event
                WHERE response_event.application_id = applications.id
                  AND response_event.event_type IN ({_response_placeholders()})
                  AND ({_newer_event_predicate("response_event", "latest_applied")})
              )
            """,
            (evaluated_at, evaluated_at, *filter_parameters, *_RESPONSE_LIKE_EVENT_TYPES),
        ).fetchall()
        return [max(0, int(row["silence_days"])) for row in rows]

    def get_funnel_metrics(
        self,
        filters: MetricsFilter | None = None,
    ) -> tuple[MetricFunnelStage, ...]:
        return (
            MetricFunnelStage(
                stage="applied",
                count=self.count_total_applications(filters=filters),
            ),
            MetricFunnelStage(
                stage="screen",
                count=self.get_response_silence_metric(filters=filters).human_response_count,
            ),
            MetricFunnelStage(
                stage="interview",
                count=self._count_distinct_companies_with_event(
                    "interview_scheduled",
                    filters=filters,
                ),
            ),
            MetricFunnelStage(
                stage="final",
                count=0,
            ),
            MetricFunnelStage(
                stage="offer",
                count=self._count_applications_with_later_event(
                    first_event_type="interview_scheduled",
                    later_event_type="offer",
                    filters=filters,
                ),
            ),
        )

    def get_application_timeseries(
        self,
        filters: MetricsFilter | None = None,
    ) -> tuple[MetricTimeseriesPoint, ...]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            SELECT substr(first_seen_at, 1, 10) AS period_start,
                COUNT(*) AS application_count
            FROM applications
            {where_clause}
            GROUP BY period_start
            ORDER BY period_start ASC
            """,
            filter_parameters,
        ).fetchall()
        return tuple(
            MetricTimeseriesPoint(
                period_start=str(row["period_start"]),
                application_count=int(row["application_count"]),
            )
            for row in rows
        )

    def get_response_rate_timeseries(
        self,
        filters: MetricsFilter | None = None,
    ) -> tuple[MetricResponseRateTrendPoint, ...]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            SELECT substr(first_seen_at, 1, 10) AS period_start,
                COUNT(*) AS application_count,
                COALESCE(SUM({_exists_response_case()}), 0) AS response_count
            FROM applications
            {where_clause}
            GROUP BY period_start
            ORDER BY period_start ASC
            """,
            (*_RESPONSE_LIKE_EVENT_TYPES, *filter_parameters),
        ).fetchall()
        return tuple(
            MetricResponseRateTrendPoint(
                period_start=str(row["period_start"]),
                application_count=int(row["application_count"]),
                response_count=int(row["response_count"]),
                response_rate=_rate_or_none(
                    numerator=int(row["response_count"]),
                    denominator=int(row["application_count"]),
                ),
            )
            for row in rows
        )

    def get_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        filters: MetricsFilter | None = None,
    ) -> tuple[MetricBreakdownRow, ...]:
        if dimension == "tech":
            return self._get_tech_breakdown(filters=filters)
        return self._get_application_breakdown(dimension, filters=filters)

    def get_response_silence_metric(
        self,
        filters: MetricsFilter | None = None,
    ) -> ResponseSilenceMetric:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
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
            {where_clause}
            """,
            (*_RESPONSE_LIKE_EVENT_TYPES, *filter_parameters),
        ).fetchone()
        total_applications = int(row["total_applications"] if row is not None else 0)
        human_response_count = int(row["human_response_count"] if row is not None else 0)
        return ResponseSilenceMetric(
            total_applications=total_applications,
            human_response_count=human_response_count,
            silent_count=total_applications - human_response_count,
        )

    def count_total_applications(self, filters: MetricsFilter | None = None) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        row = self.execute(
            f"SELECT COUNT(*) FROM applications {where_clause}",
            filter_parameters,
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_live_applications(
        self, *, active_after: str, filters: MetricsFilter | None = None
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        return self._fetch_count(
            f"""
            SELECT COUNT(*)
            FROM applications
            {where_clause}
            {"WHERE" if not where_clause else "AND"}
                current_status IN ('applied', 'in_review', 'assessment', 'interview', 'offer')
                AND last_activity_at >= ?
            """,
            (*filter_parameters, active_after),
        )

    def count_rejected_applications(self, filters: MetricsFilter | None = None) -> int:
        return self._count_applications_with_event("rejection", filters=filters)

    def count_interview_invitation_events(self, filters: MetricsFilter | None = None) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        row = self.execute(
            f"""
            SELECT COUNT(*)
            FROM application_events
            INNER JOIN applications
                ON applications.id = application_events.application_id
            WHERE event_type = 'interview_scheduled'
              {filter_clause}
            """,
            filter_parameters,
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_applications_with_interview_events(
        self,
        filters: MetricsFilter | None = None,
    ) -> int:
        return self._count_applications_with_event("interview_scheduled", filters=filters)

    def count_applications_with_offer_after_interview_events(
        self,
        filters: MetricsFilter | None = None,
    ) -> int:
        return self._count_applications_with_later_event(
            first_event_type="interview_scheduled",
            later_event_type="offer",
            filters=filters,
        )

    def _count_applications_with_current_status(
        self,
        status: str,
        filters: MetricsFilter | None = None,
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        return self._fetch_count(
            f"""
            SELECT COUNT(*)
            FROM applications
            WHERE current_status = ?
              {filter_clause}
            """,
            (status, *filter_parameters),
        )

    def _count_applications_with_event(
        self,
        event_type: str,
        filters: MetricsFilter | None = None,
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        return self._fetch_count(
            f"""
            SELECT COUNT(DISTINCT application_events.application_id)
            FROM application_events
            INNER JOIN applications
                ON applications.id = application_events.application_id
            WHERE application_events.event_type = ?
              {where_clause.replace("WHERE", "AND", 1)}
            """,
            (event_type, *filter_parameters),
        )

    def _count_distinct_companies_with_event(
        self,
        event_type: str,
        filters: MetricsFilter | None = None,
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        return self._fetch_count(
            f"""
            SELECT COUNT(DISTINCT LOWER(TRIM(applications.company)))
            FROM application_events
            INNER JOIN applications
                ON applications.id = application_events.application_id
            WHERE application_events.event_type = ?
              AND TRIM(applications.company) != ''
              {where_clause.replace("WHERE", "AND", 1)}
            """,
            (event_type, *filter_parameters),
        )

    def _count_applications_with_later_event(
        self,
        *,
        first_event_type: str,
        later_event_type: str,
        filters: MetricsFilter | None = None,
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
        return self._fetch_count(
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
                WHERE application_events.event_type IN (?, ?)
            )
            SELECT COUNT(DISTINCT first_event.application_id)
            FROM event_order AS first_event
            INNER JOIN event_order AS later_event
                ON later_event.application_id = first_event.application_id
            INNER JOIN applications
                ON applications.id = first_event.application_id
            WHERE first_event.event_type = ?
              AND later_event.event_type = ?
              {filter_clause}
              AND (
                later_event.event_at > first_event.event_at
                OR (
                    later_event.event_at = first_event.event_at
                    AND later_event.email_sent_at > first_event.email_sent_at
                )
                OR (
                    later_event.event_at = first_event.event_at
                    AND later_event.email_sent_at = first_event.email_sent_at
                    AND later_event.classified_at > first_event.classified_at
                )
                OR (
                    later_event.event_at = first_event.event_at
                    AND later_event.email_sent_at = first_event.email_sent_at
                    AND later_event.classified_at = first_event.classified_at
                    AND later_event.id > first_event.id
                )
              )
            """,
            (
                first_event_type,
                later_event_type,
                first_event_type,
                later_event_type,
                *filter_parameters,
            ),
        )

    def _get_application_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        *,
        filters: MetricsFilter | None,
    ) -> tuple[MetricBreakdownRow, ...]:
        expression = _dimension_expression(dimension)
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            SELECT {expression} AS value,
                COUNT(*) AS application_count,
                COALESCE(SUM({_exists_response_case()}), 0) AS response_count,
                COALESCE(SUM({_exists_event_case()}), 0) AS interview_count,
                COALESCE(SUM({_exists_event_case()}), 0) AS offer_count
            FROM applications
            LEFT JOIN company_profiles
                ON company_profiles.normalized_company = LOWER(TRIM(applications.company))
            {where_clause}
            GROUP BY value
            ORDER BY {_breakdown_order_expression(dimension)}
            """,
            (
                *_RESPONSE_LIKE_EVENT_TYPES,
                "interview_scheduled",
                "offer",
                *filter_parameters,
            ),
        ).fetchall()
        return tuple(_breakdown_row(dimension=dimension, row=row) for row in rows)

    def _get_tech_breakdown(
        self,
        *,
        filters: MetricsFilter | None,
    ) -> tuple[MetricBreakdownRow, ...]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            WITH tech_applications AS (
                SELECT DISTINCT
                    applications.id AS application_id,
                    LOWER(TRIM(json_each.value)) AS value
                FROM applications
                INNER JOIN json_each(applications.tech_stack)
                WHERE TRIM(json_each.value) != ''
                  {where_clause.replace("WHERE", "AND", 1)}
            )
            SELECT tech_applications.value AS value,
                COUNT(*) AS application_count,
                COALESCE(SUM(
                    CASE WHEN EXISTS (
                        SELECT 1
                        FROM application_events
                        WHERE application_events.application_id = tech_applications.application_id
                          AND application_events.event_type IN ({_response_placeholders()})
                    ) THEN 1 ELSE 0 END
                ), 0) AS response_count,
                COALESCE(SUM(
                    CASE WHEN EXISTS (
                        SELECT 1
                        FROM application_events
                        WHERE application_events.application_id = tech_applications.application_id
                          AND application_events.event_type = ?
                    ) THEN 1 ELSE 0 END
                ), 0) AS interview_count,
                COALESCE(SUM(
                    CASE WHEN EXISTS (
                        SELECT 1
                        FROM application_events
                        WHERE application_events.application_id = tech_applications.application_id
                          AND application_events.event_type = ?
                    ) THEN 1 ELSE 0 END
                ), 0) AS offer_count
            FROM tech_applications
            GROUP BY tech_applications.value
            ORDER BY value ASC
            """,
            (
                *filter_parameters,
                *_RESPONSE_LIKE_EVENT_TYPES,
                "interview_scheduled",
                "offer",
            ),
        ).fetchall()
        return tuple(_breakdown_row(dimension="tech", row=row) for row in rows)

    def _get_successful_application_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        *,
        filters: MetricsFilter | None,
    ) -> dict[str, int]:
        expression = _dimension_expression(dimension)
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            SELECT {expression} AS value,
                COUNT(*) AS success_count
            FROM applications
            LEFT JOIN company_profiles
                ON company_profiles.normalized_company = LOWER(TRIM(applications.company))
            {where_clause}
            {"WHERE" if not where_clause else "AND"} ({_exists_success_case()}) = 1
            GROUP BY value
            """,
            filter_parameters,
        ).fetchall()
        return {str(row["value"]): int(row["success_count"]) for row in rows}

    def _get_successful_tech_breakdown(
        self,
        *,
        filters: MetricsFilter | None,
    ) -> dict[str, int]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            WITH tech_applications AS (
                SELECT DISTINCT
                    applications.id AS application_id,
                    LOWER(TRIM(json_each.value)) AS value
                FROM applications
                INNER JOIN json_each(applications.tech_stack)
                WHERE TRIM(json_each.value) != ''
                  {where_clause.replace("WHERE", "AND", 1)}
            )
            SELECT tech_applications.value AS value,
                COUNT(*) AS success_count
            FROM tech_applications
            WHERE ({_exists_success_case("tech_applications.application_id")}) = 1
            GROUP BY tech_applications.value
            """,
            filter_parameters,
        ).fetchall()
        return {str(row["value"]): int(row["success_count"]) for row in rows}

    def _get_negative_application_breakdown(
        self,
        dimension: MetricsBreakdownDimension,
        *,
        filters: MetricsFilter | None,
    ) -> dict[str, int]:
        expression = _dimension_expression(dimension)
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            SELECT {expression} AS value,
                COUNT(*) AS negative_count
            FROM applications
            LEFT JOIN company_profiles
                ON company_profiles.normalized_company = LOWER(TRIM(applications.company))
            {where_clause}
            {"WHERE" if not where_clause else "AND"}
                applications.current_status IN ('rejected', 'ghosted')
            GROUP BY value
            """,
            filter_parameters,
        ).fetchall()
        return {str(row["value"]): int(row["negative_count"]) for row in rows}

    def _get_negative_tech_breakdown(
        self,
        *,
        filters: MetricsFilter | None,
    ) -> dict[str, int]:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        rows = self.execute(
            f"""
            WITH tech_applications AS (
                SELECT DISTINCT
                    applications.id AS application_id,
                    applications.current_status AS current_status,
                    LOWER(TRIM(json_each.value)) AS value
                FROM applications
                INNER JOIN json_each(applications.tech_stack)
                WHERE TRIM(json_each.value) != ''
                  {where_clause.replace("WHERE", "AND", 1)}
            )
            SELECT tech_applications.value AS value,
                COUNT(*) AS negative_count
            FROM tech_applications
            WHERE tech_applications.current_status IN ('rejected', 'ghosted')
            GROUP BY tech_applications.value
            """,
            filter_parameters,
        ).fetchall()
        return {str(row["value"]): int(row["negative_count"]) for row in rows}

    def _fetch_count(self, sql: str, parameters: Sequence[object] = ()) -> int:
        row = self.execute(sql, parameters).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_threshold_ghosted_applications(
        self,
        *,
        cutoff_at: str,
        filters: MetricsFilter | None = None,
    ) -> int:
        where_clause, filter_parameters = _metrics_filter_where_clause(filters)
        filter_clause = where_clause.replace("WHERE", "AND", 1)
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
              {filter_clause}
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
            (cutoff_at, *filter_parameters, *_RESPONSE_LIKE_EVENT_TYPES),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def map_row(self, row: sqlite3.Row) -> int:
        return int(row[0])


def _response_placeholders() -> str:
    return ", ".join("?" for _ in _RESPONSE_LIKE_EVENT_TYPES)


def _newer_event_predicate(left_alias: str, right_alias: str) -> str:
    return f"""
    {left_alias}.event_at > {right_alias}.event_at
    OR (
        {left_alias}.event_at = {right_alias}.event_at
        AND {left_alias}.email_sent_at > {right_alias}.email_sent_at
    )
    OR (
        {left_alias}.event_at = {right_alias}.event_at
        AND {left_alias}.email_sent_at = {right_alias}.email_sent_at
        AND {left_alias}.classified_at > {right_alias}.classified_at
    )
    OR (
        {left_alias}.event_at = {right_alias}.event_at
        AND {left_alias}.email_sent_at = {right_alias}.email_sent_at
        AND {left_alias}.classified_at = {right_alias}.classified_at
        AND {left_alias}.id > {right_alias}.id
    )
    """


_SILENCE_AGE_BUCKETS: tuple[tuple[SilenceAgeBucketName, int, int | None], ...] = (
    ("0_7", 0, 7),
    ("8_14", 8, 14),
    ("15_30", 15, 30),
    ("31_60", 31, 60),
    ("61_plus", 61, None),
)


def _empty_silence_age_distribution() -> dict[SilenceAgeBucketName, int]:
    return {bucket: 0 for bucket, _min_days, _max_days in _SILENCE_AGE_BUCKETS}


def _silence_age_bucket(silence_days: int) -> SilenceAgeBucketName:
    for bucket, min_days, max_days in _SILENCE_AGE_BUCKETS:
        if silence_days >= min_days and (max_days is None or silence_days <= max_days):
            return bucket
    return "61_plus"


def _rate_metric(*, name: MetricRateName, numerator: int, denominator: int) -> MetricRateRow:
    return MetricRateRow(
        name=name,
        numerator=numerator,
        denominator=denominator,
        rate=_rate_or_none(numerator=numerator, denominator=denominator),
    )


def _rate_or_none(*, numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _dimension_expression(dimension: MetricsBreakdownDimension) -> str:
    if dimension == "role":
        return "COALESCE(NULLIF(LOWER(TRIM(applications.role_title)), ''), 'unknown')"
    if dimension == "source":
        return "COALESCE(NULLIF(applications.source, ''), 'unknown')"
    if dimension == "salary":
        return """
        CASE
            WHEN applications.salary_min IS NULL AND applications.salary_max IS NULL THEN 'unknown'
            WHEN COALESCE(
                applications.salary_max,
                applications.salary_min
            ) < 100000 THEN 'under_100k'
            WHEN COALESCE(
                applications.salary_min,
                applications.salary_max
            ) >= 150000 THEN '150k_plus'
            ELSE '100k_149k'
        END
        """
    if dimension == "company_type":
        return "COALESCE(NULLIF(company_profiles.company_type, ''), 'unknown')"
    if dimension == "industry":
        return "COALESCE(NULLIF(LOWER(TRIM(company_profiles.industry)), ''), 'unknown')"
    if dimension == "sponsorship":
        return "COALESCE(NULLIF(applications.sponsorship, ''), 'unknown')"
    if dimension == "seniority":
        normalized_seniority = _normalized_seniority_expression()
        return f"""
        CASE
            WHEN TRIM(COALESCE(applications.seniority, '')) = '' THEN 'unknown'
            WHEN {normalized_seniority} LIKE '% lead %'
              OR {normalized_seniority} LIKE '% staff %'
              OR {normalized_seniority} LIKE '% principal %' THEN 'lead'
            WHEN {normalized_seniority} LIKE '% senior %'
              OR {normalized_seniority} LIKE '% sr %' THEN 'senior'
            WHEN {normalized_seniority} LIKE '% junior %'
              OR {normalized_seniority} LIKE '% jr %'
              OR {normalized_seniority} LIKE '% entry %'
              OR {normalized_seniority} LIKE '% intern %'
              OR {normalized_seniority} LIKE '% graduate %' THEN 'junior'
            WHEN {normalized_seniority} LIKE '% mid %'
              OR {normalized_seniority} LIKE '% intermediate %' THEN 'mid'
            ELSE 'unknown'
        END
        """
    if dimension == "work_mode":
        return "COALESCE(NULLIF(applications.work_mode, ''), 'unknown')"
    msg = f"Unsupported breakdown dimension: {dimension}"
    raise ValueError(msg)


def _normalized_seniority_expression() -> str:
    return """
    (' ' || REPLACE(
        REPLACE(
            REPLACE(
                REPLACE(LOWER(TRIM(COALESCE(applications.seniority, ''))), '.', ' '),
                '-',
                ' '
            ),
            '/',
            ' '
        ),
        '_',
        ' '
    ) || ' ')
    """


def _breakdown_order_expression(dimension: MetricsBreakdownDimension) -> str:
    if dimension == "seniority":
        return """
        CASE value
            WHEN 'junior' THEN 1
            WHEN 'mid' THEN 2
            WHEN 'senior' THEN 3
            WHEN 'lead' THEN 4
            WHEN 'unknown' THEN 5
            ELSE 6
        END,
        value ASC
        """
    return "value ASC"


def _metrics_filter_where_clause(filters: MetricsFilter | None) -> tuple[str, tuple[object, ...]]:
    clauses = [_submitted_application_predicate()]
    parameters: list[object] = []
    if filters is None:
        return f"WHERE {' AND '.join(clauses)}", ()
    if filters.status is not None:
        clauses.append("applications.current_status = ?")
        parameters.append(str(filters.status))
    if filters.source is not None:
        clauses.append("applications.source = ?")
        parameters.append(str(filters.source))
    if filters.sponsorship is not None:
        clauses.append("applications.sponsorship = ?")
        parameters.append(str(filters.sponsorship))
    if filters.first_seen_from is not None:
        clauses.append("applications.first_seen_at >= ?")
        parameters.append(filters.first_seen_from.isoformat())
    if filters.first_seen_to is not None:
        clauses.append("applications.first_seen_at <= ?")
        parameters.append(filters.first_seen_to.isoformat())
    if filters.role is not None:
        clauses.append("LOWER(applications.role_title) LIKE ? ESCAPE '\\'")
        parameters.append(f"%{_escape_like(filters.role.lower())}%")
    if filters.salary_min is not None:
        clauses.append("COALESCE(applications.salary_max, applications.salary_min) >= ?")
        parameters.append(filters.salary_min)
    if filters.salary_max is not None:
        clauses.append("COALESCE(applications.salary_min, applications.salary_max) <= ?")
        parameters.append(filters.salary_max)
    if filters.work_mode is not None:
        clauses.append("applications.work_mode = ?")
        parameters.append(str(filters.work_mode))

    return f"WHERE {' AND '.join(clauses)}", tuple(parameters)


def _submitted_application_predicate() -> str:
    """Exclude rows proven to come only from general job-search email.

    Canonical and manually created application rows remain valid when they have
    no classification link. Classified recruiter outreach, follow-up, and other
    job mail cannot inflate denominators if older aggregation created a row.
    """

    return """
    NOT EXISTS (
        SELECT 1
        FROM application_events AS submission_events
        INNER JOIN email_classifications AS submission_classifications
            ON submission_classifications.email_id = submission_events.email_id
        WHERE submission_events.application_id = applications.id
          AND submission_classifications.is_job_related = 1
          AND submission_classifications.category IN (
            'recruiter_outreach', 'follow_up', 'other'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM application_events AS lifecycle_events
            LEFT JOIN email_classifications AS lifecycle_classifications
                ON lifecycle_classifications.email_id = lifecycle_events.email_id
            WHERE lifecycle_events.application_id = applications.id
              AND (
                lifecycle_classifications.email_id IS NULL
                OR lifecycle_classifications.category IN (
                    'application_confirmation', 'assessment', 'interview_invite',
                    'rejection', 'offer'
                )
              )
          )
    )
    """


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


def _exists_success_case(application_id_expression: str = "applications.id") -> str:
    return f"""
    CASE WHEN EXISTS (
        SELECT 1
        FROM application_events
        WHERE application_events.application_id = {application_id_expression}
          AND application_events.event_type IN ('interview_scheduled', 'offer')
    ) THEN 1 ELSE 0 END
    """


def _breakdown_row(
    *,
    dimension: MetricsBreakdownDimension,
    row: sqlite3.Row,
) -> MetricBreakdownRow:
    application_count = int(row["application_count"])
    response_count = int(row["response_count"])
    interview_count = int(row["interview_count"])
    offer_count = int(row["offer_count"])
    return MetricBreakdownRow(
        dimension=dimension,
        value=str(row["value"]),
        application_count=application_count,
        response_count=response_count,
        response_rate=_breakdown_rate(
            numerator=response_count,
            denominator=application_count,
        ),
        interview_count=interview_count,
        interview_rate=_breakdown_rate(
            numerator=interview_count,
            denominator=application_count,
        ),
        offer_count=offer_count,
        offer_rate=_breakdown_rate(
            numerator=offer_count,
            denominator=application_count,
        ),
    )


def _breakdown_rate(*, numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
