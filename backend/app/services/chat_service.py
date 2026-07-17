from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.agent.chat_graph import ChatGraph
from app.agent.tools import SemanticSearchTool, StructuredQueryTool
from app.db.repositories import ChatRepository
from app.models.chat import ChatIncrement, ChatRequest, ChatResponse
from app.services.chat_index import ChatIndexService


class ChatService:
    """Route, ground, persist, and return one incremental local chat turn."""

    def __init__(
        self,
        *,
        history_repository: ChatRepository,
        index_service: ChatIndexService,
        structured_query: StructuredQueryTool,
        semantic_search: SemanticSearchTool,
    ) -> None:
        self._history_repository = history_repository
        self._graph = ChatGraph(
            index_service=index_service,
            structured_query=structured_query,
            semantic_search=semantic_search,
        )

    async def answer(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or uuid4().hex
        graph_result = await self._graph.run(request)
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
        return ChatResponse(
            conversation_id=conversation_id,
            route=route,
            answer=answer,
            citations=citations,
            tool_outputs=tool_outputs,
            increments=increments,
        )
