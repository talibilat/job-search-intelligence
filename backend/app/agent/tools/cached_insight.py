from __future__ import annotations

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

    def __init__(self, repository: InsightRepository) -> None:
        self._repository = repository

    def run(self, insight_type: InsightType) -> CachedInsightResult:
        insight = self._repository.get_latest_insight(insight_type, include_stale=True)
        if insight is None:
            return CachedInsightResult(insight_type=insight_type, status="missing")
        if insight.is_stale:
            return CachedInsightResult(insight_type=insight_type, status="stale")
        return CachedInsightResult(
            insight_type=insight_type,
            status="available",
            content=insight.content,
            citations=insight.citations,
        )
