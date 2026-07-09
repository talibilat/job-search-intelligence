from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_chat_history_service
from app.models import ChatHistoryResponse
from app.services.chat_history import ChatHistoryService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/history", response_model=ChatHistoryResponse)
def get_chat_history(
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
    conversation_id: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ChatHistoryResponse:
    return ChatHistoryResponse(
        messages=service.list_messages(conversation_id=conversation_id, limit=limit),
    )
