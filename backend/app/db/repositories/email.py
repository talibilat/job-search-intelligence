from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models._email_address import email_address_domain
from app.models.classification import (
    ClassificationCandidateStats,
    ClassificationReprocessingStats,
    EmailClassificationCandidate,
    EmailClassificationRecord,
)
from app.models.filter_decision import EmailCandidateQueryStrategy
from app.models.raw_email import (
    MAX_EMAIL_PREVIEW_PAGE_SIZE,
    RawEmailPreviewOrder,
    RawEmailPreviewPage,
    RawEmailPreviewRecord,
    RawEmailReaderRecord,
)
from app.models.records import (
    EmailChunkSource,
    RawEmailBodyRetentionState,
    RawEmailRecord,
)
from app.providers.email import EmailAddress, EmailMessageBody, EmailMessageMetadata


class EmailRepository(BaseRepository[RawEmailRecord]):
    """Repository seam for raw email records with typed retention validation."""

    def upsert_raw_emails(self, records: Iterable[RawEmailRecord]) -> None:
        """Write raw email rows idempotently without downgrading retained bodies."""

        record_tuple = tuple(records)
        if not record_tuple:
            return

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute_many(
                """
                INSERT INTO raw_emails (
                    id,
                    thread_id,
                    from_addr,
                    to_addr,
                    subject,
                    sent_at,
                    body_text,
                    body_retention_state,
                    labels,
                    provider,
                    ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    from_addr = excluded.from_addr,
                    to_addr = excluded.to_addr,
                    subject = excluded.subject,
                    sent_at = excluded.sent_at,
                    body_text = CASE
                        WHEN raw_emails.body_retention_state IN ('retained', 'debugging')
                            AND excluded.body_retention_state = 'metadata_only'
                        THEN raw_emails.body_text
                        ELSE excluded.body_text
                    END,
                    body_retention_state = CASE
                        WHEN raw_emails.body_retention_state IN ('retained', 'debugging')
                            AND excluded.body_retention_state = 'metadata_only'
                        THEN raw_emails.body_retention_state
                        ELSE excluded.body_retention_state
                    END,
                    labels = excluded.labels,
                    provider = excluded.provider,
                    ingested_at = excluded.ingested_at
                WHERE raw_emails.provider = excluded.provider
                """,
                [
                    (
                        record.id,
                        record.thread_id,
                        record.from_addr,
                        record.to_addr,
                        record.subject,
                        record.sent_at.isoformat() if record.sent_at is not None else None,
                        record.body_text,
                        record.body_retention_state.value,
                        json.dumps(record.labels, separators=(",", ":")),
                        record.provider,
                        record.ingested_at.isoformat(),
                    )
                    for record in record_tuple
                ],
            )

        if should_commit:
            self.connection.commit()

    def upsert_metadata_only(
        self,
        messages: tuple[EmailMessageMetadata, ...],
        *,
        ingested_at: datetime,
    ) -> int:
        """Persist provider metadata without overwriting retained body content."""

        self.upsert_raw_emails(
            RawEmailRecord(
                id=message.ref.message_id,
                thread_id=message.ref.thread_id,
                from_addr=_format_email_address(message.from_addr),
                to_addr=_format_email_addresses(message.to_addrs),
                subject=message.subject,
                sent_at=message.sent_at or message.received_at,
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
                labels=list(message.labels),
                provider=message.ref.account.provider.value,
                ingested_at=ingested_at,
            )
            for message in messages
        )
        return len(messages)

    def upsert_retained_bodies(
        self,
        bodies: Iterable[EmailMessageBody],
        *,
        retention_state: RawEmailBodyRetentionState = RawEmailBodyRetentionState.RETAINED,
    ) -> int:
        """Attach retained body text, creating a raw-email row when needed."""

        body_tuple = tuple(bodies)
        if not body_tuple:
            return 0
        if retention_state is RawEmailBodyRetentionState.METADATA_ONLY:
            msg = "retained body writes require a retained body state"
            raise ValueError(msg)

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute_many(
                """
                INSERT INTO raw_emails (
                    id,
                    thread_id,
                    from_addr,
                    to_addr,
                    subject,
                    sent_at,
                    body_text,
                    body_retention_state,
                    labels,
                    provider,
                    ingested_at
                ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?, '[]', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    body_text = excluded.body_text,
                    body_retention_state = excluded.body_retention_state
                WHERE raw_emails.provider = excluded.provider
                """,
                [
                    (
                        body.ref.message_id,
                        body.ref.thread_id,
                        body.body_text,
                        retention_state.value,
                        body.ref.account.provider.value,
                        body.fetched_at.isoformat(),
                    )
                    for body in body_tuple
                ],
            )

        if should_commit:
            self.connection.commit()
        return len(body_tuple)

    def count_raw_emails(self, *, provider: EmailProviderName | None = None) -> int:
        if provider is None:
            row = self.execute("SELECT COUNT(*) FROM raw_emails").fetchone()
        else:
            row = self.execute(
                "SELECT COUNT(*) FROM raw_emails WHERE provider = ?",
                (provider.value,),
            ).fetchone()

        if row is None:
            return 0
        return int(row[0])

    def count_raw_emails_in_window(
        self,
        *,
        sent_from: str | None = None,
        sent_before: str | None = None,
        provider: EmailProviderName | None = None,
    ) -> int:
        """Count locally stored raw emails whose sent_at falls in a window."""

        clauses: list[str] = ["sent_at IS NOT NULL"]
        parameters: list[object] = []
        if provider is not None:
            clauses.append("provider = ?")
            parameters.append(provider.value)
        if sent_from is not None:
            clauses.append("sent_at >= ?")
            parameters.append(sent_from)
        if sent_before is not None:
            clauses.append("sent_at < ?")
            parameters.append(sent_before)

        row = self.execute(
            f"SELECT COUNT(*) FROM raw_emails WHERE {' AND '.join(clauses)}",
            tuple(parameters),
        ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def list_recent_email_previews(
        self,
        *,
        provider: EmailProviderName | None = None,
        limit: int = 10,
        order_by: RawEmailPreviewOrder = RawEmailPreviewOrder.SENT_AT,
    ) -> tuple[RawEmailPreviewRecord, ...]:
        """Return recent raw-email metadata without exposing body text.

        The default order is mailbox order (newest ``sent_at`` first) so a
        resumed historical backfill does not look like an old-mail-only sync.
        ``RawEmailPreviewOrder.INGESTED_AT`` is the diagnostic view showing
        what the most recent sync run actually wrote.
        """

        if limit < 1:
            msg = "limit must be at least 1"
            raise ValueError(msg)

        parameters: tuple[object, ...]
        provider_clause = ""
        if provider is None:
            parameters = (limit,)
        else:
            provider_clause = "WHERE raw_emails.provider = ?"
            parameters = (provider.value, limit)

        order_clause = (
            "raw_emails.sent_at DESC, raw_emails.ingested_at DESC, raw_emails.id DESC"
            if order_by is RawEmailPreviewOrder.SENT_AT
            else "raw_emails.ingested_at DESC, raw_emails.sent_at DESC, raw_emails.id DESC"
        )

        columns, joins, join_parameters = self._email_preview_query_parts()
        rows = self.execute(
            f"""
            SELECT{columns}
            FROM raw_emails{joins}
            {provider_clause}
            ORDER BY {order_clause}
            LIMIT ?
            """,
            (*join_parameters, *parameters),
        ).fetchall()

        return tuple(_raw_email_preview_from_row(row) for row in rows)

    def paginate_email_previews(
        self,
        *,
        provider: EmailProviderName,
        page: int,
        page_size: int,
        sent_after: datetime | None,
        sent_before: datetime | None,
    ) -> RawEmailPreviewPage:
        """Return a deterministic page of email previews within a half-open window."""

        if page < 1:
            msg = "page must be at least 1"
            raise ValueError(msg)
        if not 1 <= page_size <= MAX_EMAIL_PREVIEW_PAGE_SIZE:
            msg = f"page_size must be between 1 and {MAX_EMAIL_PREVIEW_PAGE_SIZE}"
            raise ValueError(msg)

        clauses = ["raw_emails.provider = ?"]
        parameters: list[object] = [provider.value]
        if sent_after is not None:
            clauses.append("raw_emails.sent_at >= ?")
            parameters.append(_utc_isoformat(sent_after))
        if sent_before is not None:
            clauses.append("raw_emails.sent_at < ?")
            parameters.append(_utc_isoformat(sent_before))
        where_clause = " AND ".join(clauses)

        count_row = self.execute(
            f"SELECT COUNT(*) FROM raw_emails WHERE {where_clause}",
            tuple(parameters),
        ).fetchone()
        total_items = int(count_row[0]) if count_row is not None else 0

        columns, joins, join_parameters = self._email_preview_query_parts()
        rows = self.execute(
            f"""
            SELECT{columns}
            FROM raw_emails{joins}
            WHERE {where_clause}
            ORDER BY raw_emails.sent_at DESC, raw_emails.id DESC
            LIMIT ? OFFSET ?
            """,
            (*join_parameters, *parameters, page_size, (page - 1) * page_size),
        ).fetchall()
        return RawEmailPreviewPage(
            items=tuple(_raw_email_preview_from_row(row) for row in rows),
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=math.ceil(total_items / page_size),
        )

    def get_reader_record(
        self,
        public_id: str,
        provider: EmailProviderName,
    ) -> RawEmailReaderRecord | None:
        """Resolve one raw email through its opaque identifier and provider.

        ``body_text`` is only surfaced for retention states that are allowed
        to carry retained content, regardless of what the stored value is.
        """

        row = self.execute(
            """
            SELECT
                public_id,
                id AS provider_message_id,
                thread_id,
                from_addr,
                to_addr,
                subject,
                sent_at,
                CASE
                    WHEN body_retention_state IN ('retained', 'debugging') THEN body_text
                    ELSE NULL
                END AS body_text,
                body_retention_state,
                provider
            FROM raw_emails
            WHERE public_id = ? AND provider = ?
            """,
            (public_id, provider.value),
        ).fetchone()
        if row is None:
            return None
        return RawEmailReaderRecord.model_validate(row_to_dict(row))

    def _email_preview_query_parts(self) -> tuple[str, str, tuple[object, ...]]:
        """Return the shared preview column list, joins, and join parameters."""

        classification_columns = ""
        classification_join = ""
        if self._table_exists("email_classifications"):
            classification_columns = """,
                email_classifications.category AS classification_category,
                email_classifications.is_job_related AS classification_is_job_related"""
            classification_join = """
            LEFT JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id"""

        columns = f"""
                raw_emails.public_id,
                raw_emails.from_addr,
                raw_emails.to_addr,
                raw_emails.subject,
                raw_emails.sent_at,
                raw_emails.body_retention_state,
                CASE
                    WHEN raw_emails.body_retention_state IN ('retained', 'debugging')
                        AND raw_emails.body_text IS NOT NULL
                    THEN 1 ELSE 0
                END AS has_retained_body,
                raw_emails.provider,
                raw_emails.ingested_at,
                email_filter_decisions.outcome AS filter_outcome,
                email_filter_decisions.reason AS filter_reason{classification_columns}"""
        joins = f"""
            LEFT JOIN email_filter_decisions
                ON email_filter_decisions.email_id = raw_emails.id
                AND email_filter_decisions.strategy = ?{classification_join}"""
        return columns, joins, (EmailCandidateQueryStrategy.BROAD_JOB_SEARCH.value,)

    def get_classification_candidate_stats(
        self,
        *,
        provider: EmailProviderName,
        model: str,
        prompt_version: str,
    ) -> ClassificationCandidateStats:
        """Count retained emails needing classification for the current model and prompt."""

        if not self._table_exists("raw_emails") or not self._table_exists("email_classifications"):
            return ClassificationCandidateStats(candidate_count=0, body_text_char_count=0)

        row = self.execute(
            """
            SELECT
                COUNT(*) AS candidate_count,
                COALESCE(SUM(LENGTH(raw_emails.body_text)), 0) AS body_text_char_count
            FROM raw_emails
            LEFT JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id
            WHERE raw_emails.provider = ?
                AND raw_emails.body_retention_state = ?
                AND raw_emails.body_text IS NOT NULL
                AND LENGTH(TRIM(raw_emails.body_text)) > 0
                AND (
                    email_classifications.email_id IS NULL
                    OR email_classifications.model != ?
                    OR email_classifications.prompt_version != ?
                )
            """,
            (provider.value, RawEmailBodyRetentionState.RETAINED.value, model, prompt_version),
        ).fetchone()
        if row is None:
            return ClassificationCandidateStats(candidate_count=0, body_text_char_count=0)
        return ClassificationCandidateStats(
            candidate_count=int(row["candidate_count"]),
            body_text_char_count=int(row["body_text_char_count"]),
        )

    def get_classification_reprocessing_stats(
        self,
        *,
        provider: EmailProviderName,
        model: str,
        prompt_version: str,
    ) -> ClassificationReprocessingStats:
        """Partition retained candidates by their stored classification version."""

        if not self._table_exists("raw_emails"):
            return _empty_classification_reprocessing_stats()

        if not self._table_exists("email_classifications"):
            unclassified_count = self._count_retained_classification_candidates(
                provider=provider,
            )
            return ClassificationReprocessingStats(
                retained_candidate_count=unclassified_count,
                up_to_date_count=0,
                unclassified_count=unclassified_count,
                stale_model_count=0,
                stale_prompt_version_count=0,
                blocked_by_missing_target_model_count=0,
                reprocess_count=unclassified_count,
            )

        row = self.execute(
            """
            SELECT
                COUNT(*) AS retained_candidate_count,
                COALESCE(SUM(CASE
                    WHEN email_classifications.email_id IS NOT NULL
                        AND email_classifications.model = ?
                        AND email_classifications.prompt_version = ?
                    THEN 1 ELSE 0
                END), 0) AS up_to_date_count,
                COALESCE(SUM(CASE
                    WHEN email_classifications.email_id IS NULL
                    THEN 1 ELSE 0
                END), 0) AS unclassified_count,
                COALESCE(SUM(CASE
                    WHEN email_classifications.email_id IS NOT NULL
                        AND email_classifications.model != ?
                    THEN 1 ELSE 0
                END), 0) AS stale_model_count,
                COALESCE(SUM(CASE
                    WHEN email_classifications.email_id IS NOT NULL
                        AND email_classifications.model = ?
                        AND email_classifications.prompt_version != ?
                    THEN 1 ELSE 0
                END), 0) AS stale_prompt_version_count
            FROM raw_emails
            LEFT JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id
            WHERE raw_emails.provider = ?
                AND raw_emails.body_retention_state = ?
                AND raw_emails.body_text IS NOT NULL
            """,
            (
                model,
                prompt_version,
                model,
                model,
                prompt_version,
                provider.value,
                RawEmailBodyRetentionState.RETAINED.value,
            ),
        ).fetchone()
        if row is None:
            return _empty_classification_reprocessing_stats()

        unclassified_count = int(row["unclassified_count"])
        stale_model_count = int(row["stale_model_count"])
        stale_prompt_version_count = int(row["stale_prompt_version_count"])
        return ClassificationReprocessingStats(
            retained_candidate_count=int(row["retained_candidate_count"]),
            up_to_date_count=int(row["up_to_date_count"]),
            unclassified_count=unclassified_count,
            stale_model_count=stale_model_count,
            stale_prompt_version_count=stale_prompt_version_count,
            blocked_by_missing_target_model_count=0,
            reprocess_count=(unclassified_count + stale_model_count + stale_prompt_version_count),
        )

    def get_classification_reprocessing_stats_without_target_model(
        self,
        *,
        provider: EmailProviderName,
    ) -> ClassificationReprocessingStats:
        """Partition retained candidates when no target model is configured."""

        if not self._table_exists("raw_emails"):
            return _empty_classification_reprocessing_stats()

        if not self._table_exists("email_classifications"):
            unclassified_count = self._count_retained_classification_candidates(
                provider=provider,
            )
            return ClassificationReprocessingStats(
                retained_candidate_count=unclassified_count,
                up_to_date_count=0,
                unclassified_count=unclassified_count,
                stale_model_count=0,
                stale_prompt_version_count=0,
                blocked_by_missing_target_model_count=0,
                reprocess_count=unclassified_count,
            )

        row = self.execute(
            """
            SELECT
                COUNT(*) AS retained_candidate_count,
                COALESCE(SUM(CASE
                    WHEN email_classifications.email_id IS NULL
                    THEN 1 ELSE 0
                END), 0) AS unclassified_count,
                COALESCE(SUM(CASE
                    WHEN email_classifications.email_id IS NOT NULL
                    THEN 1 ELSE 0
                END), 0) AS blocked_by_missing_target_model_count
            FROM raw_emails
            LEFT JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id
            WHERE raw_emails.provider = ?
                AND raw_emails.body_retention_state = ?
                AND raw_emails.body_text IS NOT NULL
            """,
            (provider.value, RawEmailBodyRetentionState.RETAINED.value),
        ).fetchone()
        if row is None:
            return _empty_classification_reprocessing_stats()

        unclassified_count = int(row["unclassified_count"])
        return ClassificationReprocessingStats(
            retained_candidate_count=int(row["retained_candidate_count"]),
            up_to_date_count=0,
            unclassified_count=unclassified_count,
            stale_model_count=0,
            stale_prompt_version_count=0,
            blocked_by_missing_target_model_count=int(
                row["blocked_by_missing_target_model_count"],
            ),
            reprocess_count=unclassified_count,
        )

    def _count_retained_classification_candidates(
        self,
        *,
        provider: EmailProviderName,
    ) -> int:
        row = self.execute(
            """
            SELECT COUNT(*) AS retained_candidate_count
            FROM raw_emails
            WHERE provider = ?
                AND body_retention_state = ?
                AND body_text IS NOT NULL
            """,
            (provider.value, RawEmailBodyRetentionState.RETAINED.value),
        ).fetchone()
        if row is None:
            return 0
        return int(row["retained_candidate_count"])

    def list_classification_candidates(
        self,
        *,
        provider: EmailProviderName,
        model: str,
        prompt_version: str,
        limit: int,
        excluded_email_ids: tuple[str, ...] = (),
    ) -> list[EmailClassificationCandidate]:
        """Return retained emails needing classification for this model and prompt."""

        if limit < 1:
            msg = "limit must be at least 1"
            raise ValueError(msg)

        if not self._table_exists("raw_emails") or not self._table_exists("email_classifications"):
            return []

        exclusion_sql = ""
        parameters: list[object] = [
            provider.value,
            RawEmailBodyRetentionState.RETAINED.value,
            model,
            prompt_version,
        ]
        if excluded_email_ids:
            placeholders = ", ".join("?" for _ in excluded_email_ids)
            exclusion_sql = f" AND raw_emails.id NOT IN ({placeholders})"
            parameters.extend(excluded_email_ids)
        parameters.append(limit)

        rows = self.execute(
            f"""
            SELECT
                raw_emails.id AS email_id,
                raw_emails.subject AS subject,
                raw_emails.from_addr AS from_addr,
                raw_emails.sent_at AS sent_at,
                raw_emails.body_text AS body_text
            FROM raw_emails
            LEFT JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id
            WHERE raw_emails.provider = ?
                AND raw_emails.body_retention_state = ?
                AND raw_emails.body_text IS NOT NULL
                AND LENGTH(TRIM(raw_emails.body_text)) > 0
                AND (
                    email_classifications.email_id IS NULL
                    OR email_classifications.model != ?
                    OR email_classifications.prompt_version != ?
                )
                {exclusion_sql}
            ORDER BY raw_emails.sent_at, raw_emails.id
            LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
        candidates: list[EmailClassificationCandidate] = []
        for row in rows:
            try:
                candidates.append(EmailClassificationCandidate.model_validate(row_to_dict(row)))
            except ValidationError:
                continue
        return candidates

    def list_chunkable_retained_emails(self, *, limit: int) -> list[EmailChunkSource]:
        """Return retained job-related email bodies eligible for chunking."""

        if limit < 1:
            msg = "limit must be at least 1"
            raise ValueError(msg)

        if not self._table_exists("raw_emails") or not self._table_exists("email_classifications"):
            return []

        rows = self.execute(
            """
            SELECT
                raw_emails.id AS email_id,
                raw_emails.body_text AS body_text
            FROM raw_emails
            INNER JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id
            WHERE raw_emails.body_retention_state = ?
                AND raw_emails.body_text IS NOT NULL
                AND LENGTH(TRIM(raw_emails.body_text)) > 0
                AND email_classifications.is_job_related = 1
            ORDER BY raw_emails.sent_at, raw_emails.id
            LIMIT ?
            """,
            (RawEmailBodyRetentionState.RETAINED.value, limit),
        ).fetchall()
        return [EmailChunkSource.model_validate(row_to_dict(row)) for row in rows]

    def upsert_email_classifications(
        self,
        records: Iterable[EmailClassificationRecord],
    ) -> None:
        """Write per-email classifications idempotently by raw email ID."""

        record_tuple = tuple(records)
        if not record_tuple:
            return

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute_many(
                """
                INSERT INTO email_classifications (
                    email_id,
                    is_job_related,
                    category,
                    confidence,
                    model,
                    prompt_version,
                    classified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email_id) DO UPDATE SET
                    is_job_related = excluded.is_job_related,
                    category = excluded.category,
                    confidence = excluded.confidence,
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    classified_at = excluded.classified_at
                """,
                [
                    (
                        record.email_id,
                        int(record.is_job_related),
                        record.category.value,
                        record.confidence,
                        record.model,
                        record.prompt_version,
                        record.classified_at.isoformat(),
                    )
                    for record in record_tuple
                ],
            )

        if should_commit:
            self.connection.commit()

    def list_raw_email_ids(self, *, provider: EmailProviderName) -> list[str]:
        rows = self.execute(
            "SELECT id FROM raw_emails WHERE provider = ? ORDER BY id",
            (provider.value,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def get_thread_id(self, email_id: str) -> str | None:
        """Return the thread_id for a raw email, or None if not found."""
        row = self.execute(
            "SELECT thread_id FROM raw_emails WHERE id = ?",
            (email_id,),
        ).fetchone()
        if row is None:
            return None
        thread_id = row["thread_id"]
        return str(thread_id) if thread_id is not None else None

    def get_sent_at(self, email_id: str) -> datetime | None:
        """Return the sent_at timestamp for a raw email, or None if not found."""
        row = self.execute(
            "SELECT sent_at FROM raw_emails WHERE id = ?",
            (email_id,),
        ).fetchone()
        if row is None:
            return None
        sent_at = row["sent_at"]
        if sent_at is None:
            return None
        if isinstance(sent_at, datetime):
            return sent_at
        return datetime.fromisoformat(str(sent_at))

    def _table_exists(self, table_name: str) -> bool:
        row = self.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def map_row(self, row: sqlite3.Row) -> RawEmailRecord:
        return RawEmailRecord.model_validate(row_to_dict(row))


def _format_email_address(address: EmailAddress | None) -> str | None:
    if address is None:
        return None
    if address.display_name is None:
        return address.address
    return f"{address.display_name} <{address.address}>"


def _format_email_addresses(addresses: tuple[EmailAddress, ...]) -> str | None:
    if not addresses:
        return None
    return ", ".join(
        address for address in (_format_email_address(item) for item in addresses) if address
    )


def _raw_email_preview_from_row(row: sqlite3.Row) -> RawEmailPreviewRecord:
    row_data = row_to_dict(row)
    from_addr = row_data.pop("from_addr")
    to_addr = row_data.pop("to_addr")
    subject = row_data["subject"]
    row_data["from_domain"] = email_address_domain(from_addr)
    row_data["to_domains"] = _email_address_domains(to_addr)
    row_data["subject_present"] = bool(str(subject or "").strip())
    return RawEmailPreviewRecord.model_validate(row_data)


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        msg = "sent_after and sent_before must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC).isoformat()


def _email_address_domains(value: object) -> list[str]:
    if value is None:
        return []
    domains = {
        domain
        for domain in (email_address_domain(part) for part in str(value).split(","))
        if domain is not None
    }
    return sorted(domains)


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _empty_classification_reprocessing_stats() -> ClassificationReprocessingStats:
    return ClassificationReprocessingStats(
        retained_candidate_count=0,
        up_to_date_count=0,
        unclassified_count=0,
        stale_model_count=0,
        stale_prompt_version_count=0,
        blocked_by_missing_target_model_count=0,
        reprocess_count=0,
    )
