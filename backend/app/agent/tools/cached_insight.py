from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from app.db.repositories import InsightRepository
from app.models.insight import InsightCitation, InsightType


class CachedInsightResult(BaseModel):
    tool: Literal["cached_insight"] = "cached_insight"
    insight_type: InsightType
    status: Literal["available", "missing", "stale"]
    content: str | None = None
    citations: list[InsightCitation] = Field(default_factory=list)


class CachedInsightTool:
    """Read generated narrative insights without triggering a provider call."""

    def __init__(
        self,
        repository: InsightRepository,
        *,
        expected_cache_identity: Callable[[InsightType], tuple[str, str]] | None = None,
    ) -> None:
        self._repository = repository
        self._expected_cache_identity = expected_cache_identity

    def run(self, insight_type: InsightType) -> CachedInsightResult:
        insight = self._repository.get_latest_insight(insight_type, include_stale=True)
        if insight is None:
            return CachedInsightResult(insight_type=insight_type, status="missing")
        if self._expected_cache_identity is not None:
            inputs_hash, model = self._expected_cache_identity(insight_type)
            if insight.inputs_hash != inputs_hash or insight.model != model:
                return CachedInsightResult(insight_type=insight_type, status="stale")
        if insight.is_stale:
            return CachedInsightResult(insight_type=insight_type, status="stale")
        return CachedInsightResult(
            insight_type=insight_type,
            status="available",
            content=insight.content,
            citations=insight.citations,
        )
