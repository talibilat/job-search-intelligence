from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.agent.tools.semantic_search import normalize_sqlite_vec_embedding
from app.db.repositories import EmailChunkRepository, EmailRepository
from app.models import EmailTextChunk
from app.providers.llm import LLMEmbeddingRequest, LLMProvider, LLMProviderResponseError
from app.services.email_chunking import EmailChunkingService


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
        eligible_ids = self._chunk_repository.eligible_email_ids(limit=self._max_emails)
        self._chunk_repository.delete_email_chunks(
            self._chunk_repository.indexed_email_ids() - eligible_ids
        )
        chunks_by_email: dict[str, list[EmailTextChunk]] = defaultdict(list)
        chunks = EmailChunkingService(self._email_repository).build_chunks(limit=self._max_emails)
        for chunk in chunks:
            chunks_by_email[chunk.email_id].append(chunk)

        indexed_count = 0
        for email_id, email_chunks_list in chunks_by_email.items():
            email_chunks = tuple(email_chunks_list)
            if not self._chunk_repository.needs_indexing(
                email_id,
                email_chunks,
                provider=self._llm_provider.provider_name,
                model=self._embedding_model,
            ):
                continue
            response = await self._llm_provider.embed(
                LLMEmbeddingRequest(
                    inputs=tuple(chunk.content for chunk in email_chunks),
                    model=self._embedding_model,
                )
            )
            ordered = tuple(sorted(response.embeddings, key=lambda item: item.index))
            if tuple(item.index for item in ordered) != tuple(range(len(email_chunks))):
                raise LLMProviderResponseError(
                    public_message="The embedding provider returned an invalid response."
                )
            embeddings = tuple(normalize_sqlite_vec_embedding(item.embedding) for item in ordered)
            self._chunk_repository.replace_email_chunks(
                email_id,
                email_chunks,
                embeddings,
                provider=self._llm_provider.provider_name,
                model=self._embedding_model,
                indexed_at=datetime.now(UTC),
            )
            indexed_count += 1
        self._chunk_repository.connection.commit()
        return indexed_count
