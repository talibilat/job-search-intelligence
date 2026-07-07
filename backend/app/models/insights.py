from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.records import InsightRecord, InsightType


class InsightListResponse(BaseModel):
    insights: list[InsightRecord]


class InsightRegenerateRequest(BaseModel):
    type: InsightType
    max_evidence_items: int = Field(default=100, ge=1)


class InsightRegenerateResponse(BaseModel):
    insight: InsightRecord
    cached: bool
    evidence_citation_ids: list[str]
