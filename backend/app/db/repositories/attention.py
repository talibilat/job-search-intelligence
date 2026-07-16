from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.attention import InterviewAttentionItem, InterviewTaskCompletionResponse

_LATEST_INTERVIEWS = """
WITH ranked_interviews AS (
    SELECT
        applications.id AS application_id,
        application_events.id AS interview_event_id,
        applications.company,
        applications.role_title,
        application_events.event_at AS interview_at,
        applications.last_activity_at,
        applications.current_status,
        interview_task_completions.completed_at,
        ROW_NUMBER() OVER (
            PARTITION BY LOWER(TRIM(applications.company))
            ORDER BY application_events.event_at DESC,
                     application_events.id DESC,
                     applications.id DESC
        ) AS company_rank
    FROM applications
    INNER JOIN application_events
        ON application_events.application_id = applications.id
       AND application_events.event_type = 'interview_scheduled'
    LEFT JOIN interview_task_completions
        ON interview_task_completions.interview_event_id = application_events.id
    WHERE TRIM(applications.company) != ''
)
"""


class AttentionRepository(BaseRepository[InterviewAttentionItem]):
    """Deterministic interview-task and company-history reads."""

    def list_interviewed_companies(self) -> list[InterviewAttentionItem]:
        return self.fetch_all(
            _LATEST_INTERVIEWS
            + """
            SELECT * FROM ranked_interviews
            WHERE company_rank = 1
            ORDER BY interview_at DESC, company COLLATE NOCASE ASC
            """
        )

    def list_prepare(self, *, active_cutoff_at: str) -> list[InterviewAttentionItem]:
        return self.fetch_all(
            _LATEST_INTERVIEWS
            + """
            SELECT * FROM ranked_interviews
            WHERE company_rank = 1
              AND current_status = 'interview'
              AND completed_at IS NULL
              AND interview_at >= ?
            ORDER BY interview_at ASC, company COLLATE NOCASE ASC
            """,
            (active_cutoff_at,),
        )

    def list_follow_up(
        self,
        *,
        active_cutoff_at: str,
        follow_up_cutoff_at: str,
    ) -> list[InterviewAttentionItem]:
        return self.fetch_all(
            _LATEST_INTERVIEWS
            + """
            SELECT ranked_interviews.*
            FROM ranked_interviews
            WHERE company_rank = 1
              AND current_status = 'interview'
              AND completed_at IS NOT NULL
              AND interview_at >= ?
              AND interview_at <= ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM application_events AS later_event
                  WHERE later_event.application_id = ranked_interviews.application_id
                    AND later_event.event_at > ranked_interviews.interview_at
                    AND later_event.event_type IN (
                        'response', 'assessment', 'feedback',
                        'rejection', 'offer', 'interview_scheduled'
                    )
              )
            ORDER BY interview_at ASC, company COLLATE NOCASE ASC
            """,
            (active_cutoff_at, follow_up_cutoff_at),
        )

    def complete_interview_task(
        self,
        *,
        interview_event_id: str,
        completed_at: str,
    ) -> InterviewTaskCompletionResponse | None:
        row = self.execute(
            """
            SELECT id, application_id
            FROM application_events
            WHERE id = ? AND event_type = 'interview_scheduled'
            """,
            (interview_event_id,),
        ).fetchone()
        if row is None:
            return None
        application_id = str(row["application_id"])
        with self.transaction():
            self.execute(
                """
                INSERT INTO interview_task_completions (
                    interview_event_id, application_id, completed_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(interview_event_id) DO NOTHING
                """,
                (interview_event_id, application_id, completed_at),
            )
        saved = self.execute(
            """
            SELECT interview_event_id, application_id, completed_at
            FROM interview_task_completions
            WHERE interview_event_id = ?
            """,
            (interview_event_id,),
        ).fetchone()
        if saved is None:
            return None
        return InterviewTaskCompletionResponse.model_validate(row_to_dict(saved))

    def map_row(self, row: sqlite3.Row) -> InterviewAttentionItem:
        return InterviewAttentionItem.model_validate(row_to_dict(row))
