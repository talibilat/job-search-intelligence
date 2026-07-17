from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime

from app.db.repositories.base import BaseRepository
from app.models.chat import SemanticSearchResult
from app.models.chunk import EmailTextChunk


class EmailChunkRepository(BaseRepository[SemanticSearchResult]):
    """Persist and search retained job-email vectors in sqlite-vec."""

    def eligible_email_ids(self) -> set[str]:
        rows = self.execute(
            """
            SELECT raw_emails.id
            FROM raw_emails
            INNER JOIN email_classifications
                ON email_classifications.email_id = raw_emails.id
            WHERE raw_emails.body_retention_state = 'retained'
              AND raw_emails.body_text IS NOT NULL
              AND LENGTH(TRIM(raw_emails.body_text)) > 0
              AND email_classifications.is_job_related = 1
            ORDER BY raw_emails.sent_at, raw_emails.id
            """,
        ).fetchall()
        return {str(row[0]) for row in rows}

    def indexed_email_ids(self) -> set[str]:
        state_rows = self.execute("SELECT email_id FROM email_chunk_index_state").fetchall()
        vector_rows = self.execute("SELECT DISTINCT email_id FROM email_chunks").fetchall()
        return {str(row[0]) for row in (*state_rows, *vector_rows)}

    def needs_indexing(
        self,
        email_id: str,
        chunks: tuple[EmailTextChunk, ...],
        *,
        provider: str,
        model: str,
    ) -> bool:
        row = self.execute(
            """
            SELECT content_hash, provider, model
            FROM email_chunk_index_state
            WHERE email_id = ?
            """,
            (email_id,),
        ).fetchone()
        expected_hash = _chunks_hash(chunks)
        return row is None or tuple(row) != (expected_hash, provider, model)

    def delete_email_chunks(self, email_ids: set[str]) -> None:
        if not email_ids:
            return
        placeholders = ", ".join("?" for _ in email_ids)
        parameters = tuple(sorted(email_ids))
        self.execute(f"DELETE FROM email_chunks WHERE email_id IN ({placeholders})", parameters)
        self.execute(
            f"DELETE FROM email_chunk_index_state WHERE email_id IN ({placeholders})",
            parameters,
        )

    def replace_email_chunks(
        self,
        email_id: str,
        chunks: tuple[EmailTextChunk, ...],
        embeddings: tuple[tuple[float, ...], ...],
        *,
        provider: str,
        model: str,
        indexed_at: datetime,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunk and embedding counts must match")
        self.execute("DELETE FROM email_chunks WHERE email_id = ?", (email_id,))
        self.execute_many(
            """
            INSERT INTO email_chunks (email_id, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?)
            """,
            (
                (chunk.email_id, chunk.chunk_index, chunk.content, json.dumps(embedding))
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ),
        )
        self.execute(
            """
            INSERT INTO email_chunk_index_state (
                email_id, content_hash, provider, model, indexed_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(email_id) DO UPDATE SET
                content_hash = excluded.content_hash,
                provider = excluded.provider,
                model = excluded.model,
                indexed_at = excluded.indexed_at
            """,
            (email_id, _chunks_hash(chunks), provider, model, indexed_at.isoformat()),
        )

    def search(
        self,
        embedding: tuple[float, ...],
        *,
        limit: int,
    ) -> tuple[SemanticSearchResult, ...]:
        rows = self.execute(
            """
            SELECT
                nearest.email_id,
                nearest.chunk_index,
                nearest.content,
                nearest.distance,
                raw_emails.public_id AS email_public_id,
                raw_emails.subject,
                raw_emails.from_addr,
                raw_emails.sent_at
            FROM (
                SELECT email_id, chunk_index, content, distance
                FROM email_chunks
                WHERE embedding MATCH ? AND k = ?
            ) AS nearest
            INNER JOIN raw_emails ON raw_emails.id = nearest.email_id
            """,
            (json.dumps(embedding), limit),
        ).fetchall()
        return tuple(self._semantic_result(row) for row in rows)

    def find_all_mentioning(
        self,
        term: str,
        *,
        category: str | None = None,
    ) -> tuple[SemanticSearchResult, ...]:
        """Return one matching indexed chunk per email for an exhaustive lexical request."""

        rows = self.execute(
            """
            WITH matching_chunks AS (
                SELECT
                    email_chunks.email_id,
                    email_chunks.chunk_index,
                    email_chunks.content,
                    ROW_NUMBER() OVER (
                        PARTITION BY email_chunks.email_id
                        ORDER BY email_chunks.chunk_index
                    ) AS email_match_rank
                FROM email_chunks
                INNER JOIN email_classifications
                    ON email_classifications.email_id = email_chunks.email_id
                WHERE INSTR(LOWER(email_chunks.content), LOWER(?)) > 0
                  AND (? IS NULL OR email_classifications.category = ?)
            )
            SELECT
                matching_chunks.email_id,
                matching_chunks.chunk_index,
                matching_chunks.content,
                raw_emails.public_id AS email_public_id,
                raw_emails.subject,
                raw_emails.from_addr,
                raw_emails.sent_at
            FROM matching_chunks
            INNER JOIN raw_emails ON raw_emails.id = matching_chunks.email_id
            WHERE matching_chunks.email_match_rank = 1
            ORDER BY raw_emails.sent_at DESC, matching_chunks.email_id
            """,
            (term, category, category),
        ).fetchall()
        return tuple(self._semantic_result(row, distance=0.0) for row in rows)

    def find_companies_mentioning(self, term: str) -> tuple[SemanticSearchResult, ...]:
        """Return one cited matching email per distinct application company."""

        rows = self.execute(
            """
            WITH matching_chunks AS (
                SELECT
                    email_chunks.email_id,
                    email_chunks.chunk_index,
                    email_chunks.content,
                    ROW_NUMBER() OVER (
                        PARTITION BY email_chunks.email_id
                        ORDER BY email_chunks.chunk_index
                    ) AS email_match_rank
                FROM email_chunks
                WHERE INSTR(LOWER(email_chunks.content), LOWER(?)) > 0
            ),
            indexed_matches AS (
                SELECT
                    matching_chunks.email_id,
                    matching_chunks.chunk_index,
                    matching_chunks.content,
                    raw_emails.public_id AS email_public_id,
                    raw_emails.subject,
                    raw_emails.from_addr,
                    raw_emails.sent_at,
                    raw_emails.provider,
                    raw_emails.thread_id
                FROM matching_chunks
                INNER JOIN raw_emails
                    ON raw_emails.id = matching_chunks.email_id
                WHERE matching_chunks.email_match_rank = 1
            ),
            matching_threads AS (
                SELECT DISTINCT
                    raw_emails.provider,
                    raw_emails.thread_id,
                    application_events.application_id
                FROM application_events
                INNER JOIN raw_emails
                    ON raw_emails.id = application_events.email_id
                WHERE raw_emails.thread_id IS NOT NULL
                  AND LENGTH(TRIM(raw_emails.thread_id)) > 0
            ),
            thread_associated_matches AS (
                SELECT
                    applications.id AS application_id,
                    applications.company,
                    indexed_matches.email_id,
                    indexed_matches.chunk_index,
                    indexed_matches.content,
                    indexed_matches.email_public_id,
                    indexed_matches.subject,
                    indexed_matches.from_addr,
                    indexed_matches.sent_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            indexed_matches.email_id,
                            LOWER(TRIM(applications.company))
                        ORDER BY
                            CASE
                                WHEN applications.first_seen_at <= indexed_matches.sent_at
                                THEN 0
                                ELSE 1
                            END,
                            CASE
                                WHEN applications.first_seen_at <= indexed_matches.sent_at
                                THEN applications.first_seen_at
                            END DESC,
                            CASE
                                WHEN applications.first_seen_at > indexed_matches.sent_at
                                THEN applications.first_seen_at
                            END,
                            applications.last_activity_at DESC,
                            applications.id
                    ) AS association_rank
                FROM indexed_matches
                INNER JOIN matching_threads
                    ON matching_threads.provider = indexed_matches.provider
                    AND matching_threads.thread_id = indexed_matches.thread_id
                INNER JOIN applications
                    ON applications.id = matching_threads.application_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM application_events
                    WHERE application_events.email_id = indexed_matches.email_id
                )
            ),
            associated_matches AS (
                SELECT DISTINCT
                    applications.id AS application_id,
                    applications.company,
                    indexed_matches.email_id,
                    indexed_matches.chunk_index,
                    indexed_matches.content,
                    indexed_matches.email_public_id,
                    indexed_matches.subject,
                    indexed_matches.from_addr,
                    indexed_matches.sent_at
                FROM indexed_matches
                INNER JOIN application_events
                    ON application_events.email_id = indexed_matches.email_id
                INNER JOIN applications
                    ON applications.id = application_events.application_id
                UNION
                SELECT
                    application_id,
                    company,
                    email_id,
                    chunk_index,
                    content,
                    email_public_id,
                    subject,
                    from_addr,
                    sent_at
                FROM thread_associated_matches
                WHERE association_rank = 1
            ),
            matching_companies AS (
                SELECT
                    associated_matches.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(TRIM(associated_matches.company))
                        ORDER BY
                            associated_matches.sent_at DESC,
                            associated_matches.chunk_index,
                            associated_matches.email_id,
                            associated_matches.application_id
                    ) AS company_match_rank
                FROM associated_matches
            )
            SELECT
                application_id,
                company,
                email_id,
                chunk_index,
                content,
                email_public_id,
                subject,
                from_addr,
                sent_at
            FROM matching_companies
            WHERE company_match_rank = 1
            ORDER BY LOWER(company), company
            """,
            (term,),
        ).fetchall()
        return tuple(
            self._semantic_result(
                row,
                distance=0.0,
                company=str(row["company"]),
                application_ids=(str(row["application_id"]),),
            )
            for row in rows
        )

    def latest_for_mentioned_company(
        self,
        question: str,
    ) -> tuple[SemanticSearchResult, ...]:
        """Return newest indexed evidence when a question names a known company."""

        company_rows = self.execute(
            "SELECT DISTINCT company FROM applications ORDER BY LENGTH(company) DESC"
        ).fetchall()
        mentioned = tuple(
            str(row[0])
            for row in company_rows
            if re.search(
                rf"(?<!\w){re.escape(str(row[0]))}(?!\w)",
                question,
                flags=re.IGNORECASE,
            )
        )
        if not mentioned:
            return ()

        placeholders = ", ".join("?" for _ in mentioned)
        rows = self.execute(
            f"""
            WITH matching_applications AS (
                SELECT applications.id
                FROM applications
                WHERE applications.company IN ({placeholders})
            ),
            matching_threads AS (
                SELECT DISTINCT
                    raw_emails.provider,
                    raw_emails.thread_id,
                    application_events.application_id
                FROM application_events
                INNER JOIN matching_applications
                    ON matching_applications.id = application_events.application_id
                INNER JOIN raw_emails
                    ON raw_emails.id = application_events.email_id
                WHERE raw_emails.thread_id IS NOT NULL
                  AND LENGTH(TRIM(raw_emails.thread_id)) > 0
            ),
            matching_emails AS (
                SELECT application_events.email_id, application_events.application_id
                FROM application_events
                INNER JOIN matching_applications
                    ON matching_applications.id = application_events.application_id
                WHERE application_events.email_id IS NOT NULL
                UNION
                SELECT raw_emails.id, matching_threads.application_id
                FROM raw_emails
                INNER JOIN matching_threads
                    ON matching_threads.provider = raw_emails.provider
                    AND matching_threads.thread_id = raw_emails.thread_id
            ),
            latest_indexed_email AS (
                SELECT
                    raw_emails.id,
                    matching_emails.application_id
                FROM matching_emails
                INNER JOIN raw_emails ON raw_emails.id = matching_emails.email_id
                INNER JOIN applications
                    ON applications.id = matching_emails.application_id
                WHERE EXISTS (
                    SELECT 1
                    FROM email_chunks
                    WHERE email_chunks.email_id = raw_emails.id
                )
                ORDER BY
                    raw_emails.sent_at DESC,
                    applications.last_activity_at DESC,
                    raw_emails.id,
                    matching_emails.application_id
                LIMIT 1
            )
            SELECT
                raw_emails.id AS email_id,
                latest_indexed_email.application_id,
                0 AS chunk_index,
                raw_emails.body_text AS content,
                raw_emails.public_id AS email_public_id,
                raw_emails.subject,
                raw_emails.from_addr,
                raw_emails.sent_at
            FROM latest_indexed_email
            INNER JOIN raw_emails ON raw_emails.id = latest_indexed_email.id
            """,
            mentioned,
        ).fetchall()
        return tuple(
            self._semantic_result(
                row,
                distance=0.0,
                application_ids=(str(row["application_id"]),),
            )
            for row in rows
        )

    def _semantic_result(
        self,
        row: sqlite3.Row,
        *,
        distance: float | None = None,
        company: str | None = None,
        application_ids: tuple[str, ...] | None = None,
    ) -> SemanticSearchResult:
        if application_ids is None:
            application_rows = self.execute(
                """
                SELECT DISTINCT application_id
                FROM application_events
                WHERE email_id = ?
                ORDER BY application_id
                """,
                (row["email_id"],),
            ).fetchall()
            application_ids = tuple(str(item[0]) for item in application_rows)
        return SemanticSearchResult(
            email_public_id=row["email_public_id"],
            application_ids=application_ids,
            company=company,
            chunk_index=row["chunk_index"],
            content=row["content"],
            subject=row["subject"],
            from_addr=row["from_addr"],
            sent_at=row["sent_at"],
            distance=row["distance"] if distance is None else distance,
        )

    def map_row(self, row: sqlite3.Row) -> SemanticSearchResult:
        raise NotImplementedError


def _chunks_hash(chunks: tuple[EmailTextChunk, ...]) -> str:
    payload = "\n".join(f"{chunk.chunk_index}:{chunk.content}" for chunk in chunks)
    return hashlib.sha256(payload.encode()).hexdigest()
