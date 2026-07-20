from __future__ import annotations

import re

from app.db.repositories import EmailChunkRepository
from app.models.chat import RetrievalPlan, SemanticSearchResult
from app.providers.llm import (
    LLMEmbeddingRequest,
    LLMProvider,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)

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
        max_distance: float = 1.35,
    ) -> None:
        self._repository = repository
        self._llm_provider = llm_provider
        self._embedding_model = embedding_model
        self._max_distance = max_distance

    async def run(self, question: str, *, limit: int) -> tuple[SemanticSearchResult, ...]:
        exhaustive_request = _exhaustive_lexical_request(question)
        if exhaustive_request is not None:
            term, category, company_target = exhaustive_request
            if company_target:
                return self._repository.find_companies_mentioning(term)
            return self._repository.find_all_mentioning(term, category=category)
        if any(term in question.casefold() for term in _RECENCY_TERMS):
            latest = self._repository.latest_for_mentioned_company(question)
            if latest is not None:
                return latest
        response = await self._llm_provider.embed(
            LLMEmbeddingRequest(
                inputs=(question,),
                model=require_embedding_model(self._embedding_model),
            )
        )
        if len(response.embeddings) != 1 or response.embeddings[0].index != 0:
            raise LLMProviderResponseError(
                public_message="The embedding provider returned an invalid response."
            )
        embedding = normalize_sqlite_vec_embedding(response.embeddings[0].embedding)
        return tuple(
            item
            for item in self._repository.search(embedding, limit=limit)
            if item.distance <= self._max_distance
        )

    async def run_plan(
        self,
        plan: RetrievalPlan,
        *,
        limit: int,
    ) -> tuple[SemanticSearchResult, ...]:
        if plan.mode == "latest_company_email":
            return self._repository.latest_for_mentioned_company(plan.company or "") or ()
        if plan.mode == "exhaustive_mentions":
            term = plan.term or ""
            if plan.company_results:
                return self._repository.find_companies_mentioning(term)
            return self._repository.find_all_mentioning(term, category=plan.category)
        return await self.run(plan.query, limit=limit)


def _exhaustive_lexical_request(question: str) -> tuple[str, str | None, bool] | None:
    normalized = question.strip()
    if not re.search(r"\bevery\b", normalized, flags=re.IGNORECASE):
        return None
    match = re.search(
        r"\bmentioned\s+[\"']?(.+?)[\"']?\s*[?.!]*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    term = match.group(1).strip().strip("\"'")
    if not term:
        return None
    category = "rejection" if re.search(r"\brejections?\b", normalized, re.IGNORECASE) else None
    company_target = re.search(r"\bcompan(?:y|ies)\b", normalized, re.IGNORECASE) is not None
    return term, category, company_target


def normalize_sqlite_vec_embedding(embedding: tuple[float, ...]) -> tuple[float, ...]:
    """Pad shorter provider vectors without changing L2 or cosine ordering."""

    if len(embedding) > SQLITE_VEC_DIMENSIONS:
        raise LLMProviderResponseError(
            public_message="The configured embedding model exceeds the local vector dimensions."
        )
    return embedding + (0.0,) * (SQLITE_VEC_DIMENSIONS - len(embedding))


def require_embedding_model(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        raise LLMProviderUnavailableError(
            public_message="Configure an embedding model before using chat retrieval."
        )
    return normalized
