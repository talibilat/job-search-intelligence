from __future__ import annotations

import sqlite3

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.pipeline import PipelineStageCounts
from app.models.records import EmailBackfillStateRecord, EmailSyncStateRecord


class PipelineStatusRepository(BaseRepository[EmailBackfillStateRecord]):
    """Read-only deterministic counts and persisted sync state for pipeline status."""

    def fetch_stage_counts(self, *, provider: EmailProviderName) -> PipelineStageCounts:
        return PipelineStageCounts(
            raw_email_count=self._count(
                "SELECT COUNT(*) FROM raw_emails WHERE provider = ?",
                (provider.value,),
                table="raw_emails",
            ),
            metadata_only_count=self._count(
                """
                SELECT COUNT(*) FROM raw_emails
                WHERE provider = ? AND body_retention_state = 'metadata_only'
                """,
                (provider.value,),
                table="raw_emails",
            ),
            retained_body_count=self._count(
                """
                SELECT COUNT(*) FROM raw_emails
                WHERE provider = ? AND body_retention_state IN ('retained', 'debugging')
                """,
                (provider.value,),
                table="raw_emails",
            ),
            filter_decision_count=self._count(
                "SELECT COUNT(*) FROM email_filter_decisions",
                table="email_filter_decisions",
            ),
            filter_candidate_count=self._count(
                "SELECT COUNT(*) FROM email_filter_decisions WHERE outcome = 'candidate'",
                table="email_filter_decisions",
            ),
            filter_rejected_count=self._count(
                "SELECT COUNT(*) FROM email_filter_decisions WHERE outcome = 'rejected'",
                table="email_filter_decisions",
            ),
            classified_email_count=self._count(
                "SELECT COUNT(*) FROM email_classifications",
                table="email_classifications",
            ),
            job_related_email_count=self._count(
                "SELECT COUNT(*) FROM email_classifications WHERE is_job_related = 1",
                table="email_classifications",
            ),
            application_count=self._count(
                "SELECT COUNT(*) FROM applications",
                table="applications",
            ),
            application_event_count=self._count(
                "SELECT COUNT(*) FROM application_events",
                table="application_events",
            ),
        )

    def fetch_latest_backfill_state(
        self,
        *,
        provider: EmailProviderName,
    ) -> EmailBackfillStateRecord | None:
        if not self._table_exists("email_backfill_state"):
            return None
        return self.fetch_one(
            """
            SELECT
                provider,
                account_id,
                status,
                next_page_token,
                processed_page_count,
                processed_message_count,
                sync_cursor,
                cursor_issued_at,
                started_at,
                updated_at,
                completed_at,
                last_error
            FROM email_backfill_state
            WHERE provider = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (provider.value,),
        )

    def fetch_latest_sync_state(
        self,
        *,
        provider: EmailProviderName,
    ) -> EmailSyncStateRecord | None:
        if not self._table_exists("email_sync_state"):
            return None
        row = self.execute(
            """
            SELECT
                provider,
                account_id,
                sync_cursor,
                cursor_issued_at,
                in_progress_mode,
                next_page_token,
                updated_at
            FROM email_sync_state
            WHERE provider = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (provider.value,),
        ).fetchone()
        if row is None:
            return None
        return EmailSyncStateRecord.model_validate(row_to_dict(row))

    def map_row(self, row: sqlite3.Row) -> EmailBackfillStateRecord:
        return EmailBackfillStateRecord.model_validate(row_to_dict(row))

    def _count(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        table: str,
    ) -> int:
        if not self._table_exists(table):
            return 0
        row = self.execute(sql, parameters).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def _table_exists(self, table_name: str) -> bool:
        row = self.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None
