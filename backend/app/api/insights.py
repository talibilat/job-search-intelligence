from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_insight_generation_service, get_insight_read_service
from app.api.errors import ApiErrorResponse
from app.models import InsightRegenerateRequest
from app.models.insight import InsightListResponse, InsightRegenerateResponse
from app.services.insights_service import InsightGenerationService, InsightReadService

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get(
    "",
    response_model=InsightListResponse,
    summary="List Cached Insights",
    description=(
        "Returns the latest cached narrative insights from local SQLite, including "
        "stale records so clients can show when user-triggered regeneration is needed."
    ),
)
async def list_insights(
    service: Annotated[InsightReadService, Depends(get_insight_read_service)],
) -> InsightListResponse:
    return InsightListResponse(
        insights=service.list_latest_insights(),
        regeneration_cost_estimates=service.list_regeneration_cost_estimates(),
    )


@router.post(
    "/regenerate",
    response_model=InsightRegenerateResponse,
    summary="Regenerate Insight",
    description=(
        "Forces one cached narrative insight to be regenerated through the configured "
        "LLM provider using deterministic facts and cited evidence from local SQLite."
    ),
    responses={
        422: {"model": ApiErrorResponse},
        502: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def regenerate_insight(
    request: InsightRegenerateRequest,
    service: Annotated[
        InsightGenerationService,
        Depends(get_insight_generation_service),
    ],
) -> InsightRegenerateResponse:
    result = await service.generate_insight(
        request.type,
        max_evidence_items=request.max_evidence_items,
        force=True,
    )
    return InsightRegenerateResponse(
        insight=result.insight,
        cached=result.cached,
        evidence_citation_ids=[item.citation_id for item in result.input.evidence],
        cost=result.cost,
    )
