from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_history_service, get_chat_service
from app.api.errors import ApiErrorResponse
from app.models.chat import ChatRequest, ChatStreamEvent
from app.models.chat_history import ChatHistoryResponse
from app.providers.llm import (
    LLMProviderError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from app.providers.web_search import WebSearchProviderError
from app.services.chat_history import ChatHistoryService
from app.services.chat_service import ChatService, ChatTurnConflictError

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_class=StreamingResponse,
    responses={
        200: {
            "model": ChatStreamEvent,
            "content": {"text/event-stream": {}},
            "description": "Ordered grounded chat events.",
        },
        422: {"model": ApiErrorResponse, "description": "Request validation failed."},
        502: {"model": ApiErrorResponse, "description": "AI provider response failed."},
        503: {"model": ApiErrorResponse, "description": "AI provider unavailable."},
    },
    summary="Run Grounded Chat Turn",
    description=(
        "Routes one question through constrained deterministic metrics, cited semantic "
        "retrieval, or both. Streams route and completed-tool progress, then emits the "
        "grounded response after the complete turn is persisted."
    ),
)
async def post_chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    """Stream one grounded chat turn as server-sent events."""

    async def events() -> AsyncIterator[str]:
        try:
            async for event in service.stream(request):
                yield _sse(event)
        except LLMProviderError as error:
            yield _sse(_provider_error_event(request, error))
        except ChatTurnConflictError:
            yield _sse(
                ChatStreamEvent(
                    type="error",
                    conversation_id=request.conversation_id or "pending",
                    error_code="chat_turn_conflict",
                    error_message="This chat turn ID was already used for another question.",
                )
            )
        except WebSearchProviderError as error:
            yield _sse(
                ChatStreamEvent(
                    type="error",
                    conversation_id=request.conversation_id or "pending",
                    error_code="web_search_unavailable",
                    error_message=error.public_message,
                )
            )
        except Exception:
            yield _sse(
                ChatStreamEvent(
                    type="error",
                    conversation_id=request.conversation_id or "pending",
                    error_code="chat_internal_error",
                    error_message="The grounded chat turn could not be completed.",
                )
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: ChatStreamEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _provider_error_event(request: ChatRequest, error: LLMProviderError) -> ChatStreamEvent:
    if isinstance(error, LLMProviderUnavailableError):
        code = "llm_provider_unavailable"
    elif isinstance(error, LLMProviderTimeoutError):
        code = "llm_provider_timeout"
    elif isinstance(error, LLMProviderResponseError):
        code = "llm_provider_invalid_response"
    else:
        code = "llm_provider_request_failed"
    return ChatStreamEvent(
        type="error",
        conversation_id=request.conversation_id or "pending",
        error_code=code,
        error_message=error.public_message,
    )


@router.get("/history", response_model=ChatHistoryResponse)
def get_chat_history(
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
    conversation_id: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ChatHistoryResponse:
    return ChatHistoryResponse(
        messages=service.list_messages(conversation_id=conversation_id, limit=limit),
    )
