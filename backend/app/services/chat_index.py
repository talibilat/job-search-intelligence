from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime

from app.agent.tools.semantic_search import (
    normalize_sqlite_vec_embedding,
    require_embedding_model,
)
from app.db.repositories import EmailChunkRepository, EmailRepository
from app.models.chunk import EmailTextChunk
from app.providers.llm import LLMEmbeddingRequest, LLMProvider, LLMProviderResponseError
from app.services.email_chunking import EmailChunkingService

_MAX_CHUNKS_PER_EMBEDDING_REQUEST = 100
_RECONCILE_LOCK = asyncio.Lock()


class ChatIndexService:
    """Reconcile and embed only retained bodies classified as job-related."""

    def __init__(
        self,
        *,
        email_repository: EmailRepository,
        chunk_repository: EmailChunkRepository,
        llm_provider: LLMProvider,
        embedding_model: str,
        max_emails: int,
    ) -> None:
        self._email_repository = email_repository
        self._chunk_repository = chunk_repository
        self._llm_provider = llm_provider
        self._embedding_model = embedding_model
        self._max_emails = max_emails

    async def reconcile(self) -> int:
        async with _RECONCILE_LOCK:
            return await self._reconcile()

    async def _reconcile(self) -> int:
        eligible_ids = self._chunk_repository.eligible_email_ids()
        self._chunk_repository.delete_email_chunks(
            self._chunk_repository.indexed_email_ids() - eligible_ids
        )

        indexed_count = 0
        chunking_service = EmailChunkingService(self._email_repository)
        for offset in range(0, len(eligible_ids), self._max_emails):
            chunks_by_email: dict[str, list[EmailTextChunk]] = defaultdict(list)
            chunks = chunking_service.build_chunks(limit=self._max_emails, offset=offset)
            for chunk in chunks:
                chunks_by_email[chunk.email_id].append(chunk)

            pending_chunks: list[EmailTextChunk] = []
            pending_by_email: dict[str, tuple[EmailTextChunk, ...]] = {}
            for email_id, email_chunks_list in chunks_by_email.items():
                email_chunks = tuple(email_chunks_list)
                if not self._chunk_repository.needs_indexing(
                    email_id,
                    email_chunks,
                    provider=self._llm_provider.provider_name,
                    model=self._embedding_model,
                ):
                    continue
                pending_by_email[email_id] = email_chunks
                pending_chunks.extend(email_chunks)

            embeddings_by_chunk: dict[tuple[str, int], tuple[float, ...]] = {}
            for batch_start in range(
                0,
                len(pending_chunks),
                _MAX_CHUNKS_PER_EMBEDDING_REQUEST,
            ):
                batch = pending_chunks[
                    batch_start : batch_start + _MAX_CHUNKS_PER_EMBEDDING_REQUEST
                ]
                response = await self._llm_provider.embed(
                    LLMEmbeddingRequest(
                        inputs=tuple(chunk.content for chunk in batch),
                        model=require_embedding_model(self._embedding_model),
                    )
                )
                ordered = tuple(sorted(response.embeddings, key=lambda item: item.index))
                if tuple(item.index for item in ordered) != tuple(range(len(batch))):
                    raise LLMProviderResponseError(
                        public_message="The embedding provider returned an invalid response."
                    )
                for chunk, embedding in zip(batch, ordered, strict=True):
                    embeddings_by_chunk[(chunk.email_id, chunk.chunk_index)] = (
                        normalize_sqlite_vec_embedding(embedding.embedding)
                    )

            for email_id, email_chunks in pending_by_email.items():
                self._chunk_repository.replace_email_chunks(
                    email_id,
                    email_chunks,
                    tuple(
                        embeddings_by_chunk[(chunk.email_id, chunk.chunk_index)]
                        for chunk in email_chunks
                    ),
                    provider=self._llm_provider.provider_name,
                    model=self._embedding_model,
                    indexed_at=datetime.now(UTC),
                )
                indexed_count += 1
        self._chunk_repository.connection.commit()
        return indexed_count
