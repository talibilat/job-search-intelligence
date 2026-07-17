from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from app.agent.chat_graph import ChatGraph, ChatGraphState
from app.agent.tools import CachedInsightTool, SemanticSearchTool, StructuredQueryTool
from app.db.repositories import ChatRepository
from app.models.chat import ChatIncrement, ChatRequest, ChatResponse, ChatStreamEvent
from app.services.chat_index import ChatIndexService

_CONTEXT_REFERENCE_PATTERN = re.compile(
    r"\b(?:it|its|they|them|their|theirs|that|those|there|this)\b",
    flags=re.IGNORECASE,
)
_CONTEXT_PREFIXES = ("and ", "how about ", "what about ")


class ChatService:
    """Route, ground, persist, and return one incremental local chat turn."""

    def __init__(
        self,
        *,
        history_repository: ChatRepository,
        index_service: ChatIndexService,
        structured_query: StructuredQueryTool,
        semantic_search: SemanticSearchTool,
        cached_insight: CachedInsightTool,
    ) -> None:
        self._history_repository = history_repository
        self._graph = ChatGraph(
            index_service=index_service,
            structured_query=structured_query,
            semantic_search=semantic_search,
            cached_insight=cached_insight,
        )

    async def answer(self, request: ChatRequest) -> ChatResponse:
        response: ChatResponse | None = None
        async for event in self.stream(request):
            if event.type == "complete":
                response = event.response
        if response is None:  # pragma: no cover - the compiled graph always synthesizes
            raise RuntimeError("Chat graph completed without an answer.")
        return response

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        conversation_id = request.conversation_id or uuid4().hex
        graph_request = self._with_conversation_context(request)
        graph_result = ChatGraphState(request=graph_request)
        async for node, update in self._graph.stream(graph_request):
            graph_result.update(update)
            if node == "route":
                route = update["route"]
                yield ChatStreamEvent(
                    type="route",
                    conversation_id=conversation_id,
                    route=route,
                )
            elif node in {
                "structured_query",
                "semantic_search",
                "cached_insight",
                "mixed_tools",
                "mixed_cached_insight",
            }:
                for output in update.get("tool_outputs", []):
                    tool = output.get("tool")
                    if tool in {"structured_query", "semantic_search", "cached_insight"}:
                        yield ChatStreamEvent(
                            type="tool",
                            conversation_id=conversation_id,
                            tool=cast(
                                "Literal['structured_query', 'semantic_search', 'cached_insight']",
                                tool,
                            ),
                        )

        route = graph_result["route"]
        tool_outputs = graph_result.get("tool_outputs", [])
        citations = graph_result.get("citations", [])
        answer = graph_result["answer"]
        increments = [
            ChatIncrement(type="route", content=route),
            *(ChatIncrement(type="tool", content=str(output["tool"])) for output in tool_outputs),
            ChatIncrement(type="answer", content=answer),
        ]
        now = datetime.now(UTC)
        citation_payload = [item.model_dump(mode="json", exclude_none=True) for item in citations]
        self._history_repository.add_message(
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            citations=[],
            tool_outputs=[],
            created_at=now,
        )
        for output in tool_outputs:
            self._history_repository.add_message(
                conversation_id=conversation_id,
                role="tool",
                content=str(output["tool"]),
                citations=[],
                tool_outputs=[output],
                created_at=now,
            )
        self._history_repository.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            citations=citation_payload,
            tool_outputs=tool_outputs,
            created_at=now,
        )
        self._history_repository.connection.commit()
        response = ChatResponse(
            conversation_id=conversation_id,
            route=route,
            answer=answer,
            citations=citations,
            tool_outputs=tool_outputs,
            increments=increments,
        )
        yield ChatStreamEvent(
            type="complete",
            conversation_id=conversation_id,
            response=response,
        )

    def _with_conversation_context(self, request: ChatRequest) -> ChatRequest:
        if request.conversation_id is None or not _needs_conversation_context(request.message):
            return request
        history = self._history_repository.list_messages(
            conversation_id=request.conversation_id,
            limit=20,
        )
        previous_questions: list[str] = []
        for message in reversed(history):
            if message.role != "user":
                continue
            previous_questions.append(message.content)
            if not _needs_conversation_context(message.content):
                break
        if not previous_questions:
            return request
        context = "\n".join(
            f"Previous user question: {question}" for question in previous_questions
        )
        return request.model_copy(
            update={"message": (f"{context}\nCurrent user question: {request.message}")}
        )


def _needs_conversation_context(message: str) -> bool:
    normalized = message.casefold().lstrip()
    return _CONTEXT_REFERENCE_PATTERN.search(message) is not None or normalized.startswith(
        _CONTEXT_PREFIXES
    )
