from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_insight_generation_service, get_insight_repository
from app.db.repositories import InsightRepository
from app.models import (
    InsightListResponse,
    InsightRegenerateRequest,
    InsightRegenerateResponse,
)
from app.services.insights_service import InsightGenerationService

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get(
    "",
    response_model=InsightListResponse,
    summary="List Cached Insights",
    description="Returns fresh cached narrative insights from local SQLite without calling an LLM.",
)
def list_insights(
    insight_repository: Annotated[
        InsightRepository,
        Depends(get_insight_repository),
    ],
) -> InsightListResponse:
    return InsightListResponse(insights=insight_repository.list_latest_insights())


@router.post(
    "/regenerate",
    response_model=InsightRegenerateResponse,
    summary="Regenerate Insight",
    description=(
        "Regenerates one cached narrative insight through the configured LLM provider "
        "using deterministic facts and cited source evidence."
    ),
)
async def regenerate_insight(
    request: InsightRegenerateRequest,
    insight_service: Annotated[
        InsightGenerationService,
        Depends(get_insight_generation_service),
    ],
) -> InsightRegenerateResponse:
    result = await insight_service.generate_insight(
        request.type,
        max_evidence_items=request.max_evidence_items,
        force=True,
    )
    return InsightRegenerateResponse(
        insight=result.insight,
        cached=result.cached,
        evidence_citation_ids=[item.citation_id for item in result.input.evidence],
    )
