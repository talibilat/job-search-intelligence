from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from app.db.repositories.base import BaseRepository
from app.models import EmailTextChunk
from app.models.chat import SemanticSearchResult


class EmailChunkRepository(BaseRepository[SemanticSearchResult]):
    """Persist and search retained job-email vectors in sqlite-vec."""

    def eligible_email_ids(self, *, limit: int) -> set[str]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
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
            LIMIT ?
            """,
            (limit,),
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
        results: list[SemanticSearchResult] = []
        for row in rows:
            application_rows = self.execute(
                """
                SELECT DISTINCT application_id
                FROM application_events
                WHERE email_id = ?
                ORDER BY application_id
                """,
                (row["email_id"],),
            ).fetchall()
            results.append(
                SemanticSearchResult(
                    email_public_id=row["email_public_id"],
                    application_ids=tuple(str(item[0]) for item in application_rows),
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    subject=row["subject"],
                    from_addr=row["from_addr"],
                    sent_at=row["sent_at"],
                    distance=row["distance"],
                )
            )
        return tuple(results)

    def map_row(self, row: sqlite3.Row) -> SemanticSearchResult:
        raise NotImplementedError


def _chunks_hash(chunks: tuple[EmailTextChunk, ...]) -> str:
    payload = "\n".join(f"{chunk.chunk_index}:{chunk.content}" for chunk in chunks)
    return hashlib.sha256(payload.encode()).hexdigest()
