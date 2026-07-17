from __future__ import annotations

from app.db.repositories import EmailChunkRepository
from app.models.chat import SemanticSearchResult
from app.providers.llm import LLMEmbeddingRequest, LLMProvider, LLMProviderResponseError

SQLITE_VEC_DIMENSIONS = 1536
_RECENCY_TERMS = ("last email", "latest email", "most recent email")


class SemanticSearchTool:
    """Embed a question through the configured adapter and search local sqlite-vec data."""

    def __init__(
        self,
        *,
        repository: EmailChunkRepository,
        llm_provider: LLMProvider,
        embedding_model: str,
    ) -> None:
        self._repository = repository
        self._llm_provider = llm_provider
        self._embedding_model = embedding_model

    async def run(self, question: str, *, limit: int) -> tuple[SemanticSearchResult, ...]:
        if any(term in question.casefold() for term in _RECENCY_TERMS):
            latest = self._repository.latest_for_mentioned_company(question, limit=limit)
            if latest:
                return latest
        response = await self._llm_provider.embed(
            LLMEmbeddingRequest(inputs=(question,), model=self._embedding_model)
        )
        if len(response.embeddings) != 1 or response.embeddings[0].index != 0:
            raise LLMProviderResponseError(
                public_message="The embedding provider returned an invalid response."
            )
        embedding = normalize_sqlite_vec_embedding(response.embeddings[0].embedding)
        return self._repository.search(embedding, limit=limit)


def normalize_sqlite_vec_embedding(embedding: tuple[float, ...]) -> tuple[float, ...]:
    """Pad shorter provider vectors without changing L2 or cosine ordering."""

    if len(embedding) > SQLITE_VEC_DIMENSIONS:
        raise LLMProviderResponseError(
            public_message="The configured embedding model exceeds the local vector dimensions."
        )
    return embedding + (0.0,) * (SQLITE_VEC_DIMENSIONS - len(embedding))
