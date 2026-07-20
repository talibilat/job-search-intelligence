from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from app.agent.chat_graph import ChatGraph, ChatGraphState, synthesize_grounded_answer
from app.agent.planner import ChatPlanner
from app.agent.synthesis import ChatSynthesizer, cited_ids
from app.agent.tools import (
    CachedInsightTool,
    SemanticSearchTool,
    StructuredQueryTool,
    WebSearchTool,
)
from app.db.repositories import ChatRepository
from app.models.chat import (
    ChatCitation,
    ChatFollowUpPrompt,
    ChatIncrement,
    ChatMessageRecord,
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
)
from app.services.chat_index import ChatIndexService

_CONTEXT_REFERENCE_PATTERN = re.compile(
    r"\b(?:it|its|they|them|their|theirs|that|those|there|this)\b",
    flags=re.IGNORECASE,
)
_CONTEXT_PREFIXES = ("and ", "how about ", "what about ")
_TURN_LOCKS: dict[str, asyncio.Lock] = {}


class ChatTurnConflictError(RuntimeError):
    """Raised when one idempotency key is reused for a different turn."""


class ChatService:
    """Route, ground, persist, and return one incremental local chat turn."""

    def __init__(
        self,
        *,
        history_repository: ChatRepository,
        planner: ChatPlanner,
        synthesizer: ChatSynthesizer,
        index_service: ChatIndexService,
        structured_query: StructuredQueryTool,
        semantic_search: SemanticSearchTool,
        cached_insight: CachedInsightTool,
        web_search: WebSearchTool,
    ) -> None:
        self._history_repository = history_repository
        self._synthesizer = synthesizer
        self._graph = ChatGraph(
            planner=planner,
            index_service=index_service,
            structured_query=structured_query,
            semantic_search=semantic_search,
            cached_insight=cached_insight,
            web_search=web_search,
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
        lock = _TURN_LOCKS.setdefault(request.turn_id, asyncio.Lock())
        async with lock:
            async for event in self._stream_locked(request):
                yield event

    async def _stream_locked(self, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        completed = self._history_repository.get_completed_assistant_turn(
            turn_id=request.turn_id,
            conversation_id=request.conversation_id,
        )
        if completed is not None:
            original = self._history_repository.get_user_turn(turn_id=request.turn_id)
            if (
                original is None
                or original.content != request.message
                or (
                    request.conversation_id is not None
                    and original.conversation_id != request.conversation_id
                )
            ):
                raise ChatTurnConflictError
            response = self._response_from_completed_turn(completed)
            yield ChatStreamEvent(
                type="answer_delta",
                conversation_id=response.conversation_id,
                answer_delta=response.answer,
            )
            yield ChatStreamEvent(
                type="complete",
                conversation_id=response.conversation_id,
                response=response,
            )
            return

        conversation_id = request.conversation_id or uuid4().hex
        history = self._history_repository.list_messages(
            conversation_id=conversation_id,
            limit=40,
        )
        graph_result = ChatGraphState(request=request, history=history)
        async for node, update in self._graph.stream(request, history=history):
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
                "conversation",
                "web_search",
            }:
                for output in update.get("tool_outputs", []):
                    tool = output.get("tool")
                    if tool in {
                        "structured_query",
                        "semantic_search",
                        "cached_insight",
                        "web_search",
                    }:
                        yield ChatStreamEvent(
                            type="tool",
                            conversation_id=conversation_id,
                            tool=cast(
                                "Literal['structured_query', 'semantic_search', "
                                "'cached_insight', 'web_search']",
                                tool,
                            ),
                        )

        route = graph_result["route"]
        tool_outputs = graph_result.get("tool_outputs", [])
        citations = graph_result.get("citations", [])
        content_results = graph_result.get("content_results", ())
        web_results = graph_result.get("web_results", ())
        answer_parts: list[str] = []
        answer_kind: Literal["conversation", "grounded", "refusal"] = "grounded"
        follow_up_prompts: list[ChatFollowUpPrompt] = []
        plan = graph_result["plan"]
        exhaustive_retrieval = (
            plan.retrieval is not None and plan.retrieval.mode == "exhaustive_mentions"
        )
        if route == "conversation":
            conversation = await self._synthesizer.generate_conversation(
                question=request.message,
                history=history,
            )
            answer_kind = "conversation"
            follow_up_prompts = list(conversation.follow_up_prompts)
            answer_parts.append(conversation.answer)
            yield ChatStreamEvent(
                type="answer_delta",
                conversation_id=conversation_id,
                answer_delta=conversation.answer,
            )
        elif content_results and exhaustive_retrieval:
            answer = synthesize_grounded_answer(route, tool_outputs, content_results, citations)
            answer_parts.append(answer)
            yield ChatStreamEvent(
                type="answer_delta",
                conversation_id=conversation_id,
                answer_delta=answer,
            )
        elif content_results or web_results:
            metric_outputs = [
                output for output in tool_outputs if output.get("tool") == "structured_query"
            ]
            metric_citations = [item for item in citations if item.source == "metric"]
            if metric_outputs:
                metric_answer = synthesize_grounded_answer(
                    "quantitative",
                    metric_outputs,
                    (),
                    metric_citations,
                )
                answer_parts.append(f"{metric_answer}\n\n")
                yield ChatStreamEvent(
                    type="answer_delta",
                    conversation_id=conversation_id,
                    answer_delta=f"{metric_answer}\n\n",
                )
            if content_results:
                async for delta in self._synthesizer.stream(
                    question=request.message,
                    history=history,
                    evidence=content_results,
                    citations=[item for item in citations if item.source == "email"],
                ):
                    answer_parts.append(delta)
                    yield ChatStreamEvent(
                        type="answer_delta",
                        conversation_id=conversation_id,
                        answer_delta=delta,
                    )
            if web_results:
                if content_results:
                    answer_parts.append("\n\n")
                    yield ChatStreamEvent(
                        type="answer_delta",
                        conversation_id=conversation_id,
                        answer_delta="\n\n",
                    )
                async for delta in self._synthesizer.stream_web(
                    question=request.message,
                    history=history,
                    evidence=web_results,
                    citations=[item for item in citations if item.source == "web"],
                ):
                    answer_parts.append(delta)
                    yield ChatStreamEvent(
                        type="answer_delta",
                        conversation_id=conversation_id,
                        answer_delta=delta,
                    )
        else:
            answer = (
                "INSUFFICIENT_EVIDENCE: Web search returned no citable results."
                if route == "web"
                else synthesize_grounded_answer(route, tool_outputs, (), citations)
            )
            if route in {"content", "web", "mixed"} and not citations:
                answer_kind = "refusal"
            answer_parts.append(answer)
            yield ChatStreamEvent(
                type="answer_delta",
                conversation_id=conversation_id,
                answer_delta=answer,
            )
        answer = "".join(answer_parts).strip()
        if answer.startswith("INSUFFICIENT_EVIDENCE:"):
            answer_kind = "refusal"
        if not follow_up_prompts:
            follow_up_prompts = _deterministic_follow_up_prompts(tool_outputs)
        used_citation_ids = cited_ids(answer)
        should_filter_citations = any(
            output.get("tool") in {"semantic_search", "web_search"} for output in tool_outputs
        ) or any(
            output.get("tool") == "structured_query"
            and output.get("template") == "live_applications"
            for output in tool_outputs
        )
        if should_filter_citations:
            citations = [
                item
                for item in citations
                if item.source == "metric" or item.citation_id in used_citation_ids
            ]
        increments = [
            ChatIncrement(type="route", content=route),
            *(ChatIncrement(type="tool", content=str(output["tool"])) for output in tool_outputs),
            ChatIncrement(type="answer", content=answer),
        ]
        now = datetime.now(UTC)
        citation_payload = [item.model_dump(mode="json", exclude_none=True) for item in citations]
        self._history_repository.add_message(
            conversation_id=conversation_id,
            turn_id=request.turn_id,
            role="user",
            content=request.message,
            citations=[],
            tool_outputs=[],
            created_at=now,
        )
        for output in tool_outputs:
            self._history_repository.add_message(
                conversation_id=conversation_id,
                turn_id=request.turn_id,
                role="tool",
                content=str(output["tool"]),
                citations=[],
                tool_outputs=[output],
                created_at=now,
            )
        self._history_repository.add_message(
            conversation_id=conversation_id,
            turn_id=request.turn_id,
            role="assistant",
            route=route,
            answer_kind=answer_kind,
            content=answer,
            citations=citation_payload,
            tool_outputs=tool_outputs,
            follow_up_prompts=[item.model_dump(mode="json") for item in follow_up_prompts],
            created_at=now,
        )
        self._history_repository.connection.commit()
        response = ChatResponse(
            conversation_id=conversation_id,
            route=route,
            answer=answer,
            answer_kind=answer_kind,
            citations=citations,
            tool_outputs=tool_outputs,
            increments=increments,
            follow_up_prompts=follow_up_prompts,
        )
        yield ChatStreamEvent(
            type="complete",
            conversation_id=conversation_id,
            response=response,
        )

    @staticmethod
    def _response_from_completed_turn(record: ChatMessageRecord) -> ChatResponse:
        if record.route is None:  # pragma: no cover - repository lookup requires route
            raise RuntimeError("completed assistant turn is missing its route")
        citations = [ChatCitation.model_validate(item) for item in record.citations_json]
        tool_outputs = list(record.tool_outputs_json)
        follow_up_prompts = [
            ChatFollowUpPrompt.model_validate(item) for item in record.follow_up_prompts_json
        ]
        return ChatResponse(
            conversation_id=record.conversation_id,
            route=record.route,
            answer=record.content,
            answer_kind=record.answer_kind or ("grounded" if citations else "refusal"),
            citations=citations,
            tool_outputs=tool_outputs,
            increments=[
                ChatIncrement(type="route", content=record.route),
                *(
                    ChatIncrement(type="tool", content=str(output.get("tool", "tool")))
                    for output in tool_outputs
                ),
                ChatIncrement(type="answer", content=record.content),
            ],
            follow_up_prompts=follow_up_prompts,
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


def _deterministic_follow_up_prompts(
    tool_outputs: list[dict[str, object]],
) -> list[ChatFollowUpPrompt]:
    structured = next(
        (item for item in tool_outputs if item.get("tool") == "structured_query"),
        None,
    )
    if structured is None:
        return []
    template = structured.get("template")
    if template in {"summary_counts", "total_applications"}:
        return [
            ChatFollowUpPrompt(
                label="Show those applications",
                message="Show me the applications included in that count.",
            )
        ]
    if template == "application_list":
        return [
            ChatFollowUpPrompt(
                label="Group by company",
                message="Group these applications by company.",
            )
        ]
    if template == "company_list":
        return [
            ChatFollowUpPrompt(
                label="Show application details",
                message="Show the applications for these companies.",
            )
        ]
    return []


def _needs_conversation_context(message: str) -> bool:
    normalized = message.casefold().lstrip()
    return _CONTEXT_REFERENCE_PATTERN.search(message) is not None or normalized.startswith(
        _CONTEXT_PREFIXES
    )
