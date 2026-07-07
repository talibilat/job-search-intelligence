from __future__ import annotations

import sqlite3

from app.db.repositories.base import BaseRepository
from app.models.event import RESPONSE_LIKE_APPLICATION_EVENT_TYPES
from app.models.metrics import ResponseSilenceMetric

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
        row = self.execute(
            """
            SELECT COUNT(DISTINCT application_events.application_id)
            FROM application_events
            INNER JOIN applications
                ON applications.id = application_events.application_id
            WHERE application_events.event_type = 'offer'
            """,
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

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
        row = self.execute(
            "SELECT COUNT(*) FROM applications WHERE current_status = ?",
            ("rejected",),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

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
