from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_chat_history_service, get_chat_service
from app.api.errors import ApiErrorResponse
from app.models import ChatResponse
from app.models.chat import ChatRequest
from app.models.chat_history import ChatHistoryResponse
from app.services.chat_history import ChatHistoryService
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    responses={
        422: {"model": ApiErrorResponse, "description": "Request validation failed."},
        502: {"model": ApiErrorResponse, "description": "AI provider response failed."},
        503: {"model": ApiErrorResponse, "description": "AI provider unavailable."},
    },
    summary="Run Grounded Chat Turn",
    description=(
        "Routes one question through constrained deterministic metrics, cited semantic "
        "retrieval, or both. Returns ordered route, tool, and answer increments after the "
        "complete turn is persisted."
    ),
)
async def post_chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    """Return ordered route/tool/answer increments for one grounded chat turn."""

    return await service.answer(request)


@router.get("/history", response_model=ChatHistoryResponse)
def get_chat_history(
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
    conversation_id: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ChatHistoryResponse:
    return ChatHistoryResponse(
        messages=service.list_messages(conversation_id=conversation_id, limit=limit),
    )
