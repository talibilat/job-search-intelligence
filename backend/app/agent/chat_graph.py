from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.agent.tools import SemanticSearchTool, StructuredQueryRequest, StructuredQueryTool
from app.models.chat import ChatCitation, ChatRequest, ChatRoute, SemanticSearchResult
from app.services.chat_index import ChatIndexService

_QUANTITATIVE_TERMS = (
    "how many",
    "count",
    "rate",
    "funnel",
    "conversion",
    "waiting on",
    "overdue",
    "follow-up",
    "follow up",
    "which roles",
    "which sources",
)
_CONTENT_TERMS = (
    "exactly",
    "email",
    "recruiter",
    "said",
    "say",
    "mentioned",
    "feedback",
    "why",
)
type ToolOutput = dict[str, object]
type ToolBranch = Literal["quantitative", "content", "mixed"]


class ChatGraphState(TypedDict, total=False):
    request: ChatRequest
    route: ChatRoute
    tool_outputs: list[ToolOutput]
    citations: list[ChatCitation]
    content_results: tuple[SemanticSearchResult, ...]
    answer: str


class ChatGraph:
    """Typed LangGraph orchestration over constrained local chat tools."""

    def __init__(
        self,
        *,
        index_service: ChatIndexService,
        structured_query: StructuredQueryTool,
        semantic_search: SemanticSearchTool,
    ) -> None:
        self._index_service = index_service
        self._structured_query = structured_query
        self._semantic_search = semantic_search

        builder = StateGraph(ChatGraphState)
        builder.add_node("route", self._route)
        builder.add_node("structured_query", self._run_structured_query)
        builder.add_node("semantic_search", self._run_semantic_search)
        builder.add_node("mixed_tools", self._run_mixed_tools)
        builder.add_node("synthesize", self._synthesize)
        builder.add_edge(START, "route")
        builder.add_conditional_edges(
            "route",
            self._tool_branch,
            {
                "quantitative": "structured_query",
                "content": "semantic_search",
                "mixed": "mixed_tools",
            },
        )
        builder.add_edge("structured_query", "synthesize")
        builder.add_edge("semantic_search", "synthesize")
        builder.add_edge("mixed_tools", "synthesize")
        builder.add_edge("synthesize", END)
        self._graph = builder.compile()

    async def run(self, request: ChatRequest) -> ChatGraphState:
        result = await self._graph.ainvoke({"request": request})
        return cast(ChatGraphState, result)

    async def stream(self, request: ChatRequest) -> AsyncIterator[tuple[str, ChatGraphState]]:
        async for update in self._graph.astream(
            {"request": request},
            stream_mode="updates",
        ):
            for node, state_update in update.items():
                yield node, cast(ChatGraphState, state_update)

    def _route(self, state: ChatGraphState) -> ChatGraphState:
        return {"route": route_question(state["request"].message)}

    def _tool_branch(self, state: ChatGraphState) -> ToolBranch:
        return state["route"]

    def _run_structured_query(self, state: ChatGraphState) -> ChatGraphState:
        output, citations = self._structured_result(state["request"].message)
        return {"tool_outputs": [output], "citations": citations, "content_results": ()}

    async def _run_semantic_search(self, state: ChatGraphState) -> ChatGraphState:
        results, output, citations = await self._semantic_result(state["request"])
        return {
            "tool_outputs": [output],
            "citations": citations,
            "content_results": results,
        }

    async def _run_mixed_tools(self, state: ChatGraphState) -> ChatGraphState:
        request = state["request"]
        structured_output, structured_citations = self._structured_result(request.message)
        results, semantic_output, semantic_citations = await self._semantic_result(request)
        return {
            "tool_outputs": [structured_output, semantic_output],
            "citations": [*structured_citations, *semantic_citations],
            "content_results": results,
        }

    def _structured_result(self, question: str) -> tuple[ToolOutput, list[ChatCitation]]:
        result = self._structured_query.run(_structured_request(question))
        output = result.model_dump(mode="json")
        return output, _structured_citations(result.template, output)

    async def _semantic_result(
        self, request: ChatRequest
    ) -> tuple[tuple[SemanticSearchResult, ...], ToolOutput, list[ChatCitation]]:
        await self._index_service.reconcile()
        results = await self._semantic_search.run(
            request.message,
            limit=request.retrieval_limit,
        )
        output: ToolOutput = {
            "tool": "semantic_search",
            "results": [item.model_dump(mode="json", exclude={"content"}) for item in results],
        }
        citations = [
            ChatCitation(
                citation_id=f"email:{item.email_public_id}:{item.chunk_index}",
                source="email",
                email_public_id=item.email_public_id,
                application_id=item.application_ids[0] if item.application_ids else None,
                subject=item.subject,
                sent_at=item.sent_at,
                snippet=" ".join(item.content.split())[:280],
            )
            for item in results
        ]
        return results, output, citations

    def _synthesize(self, state: ChatGraphState) -> ChatGraphState:
        return {
            "answer": synthesize_grounded_answer(
                state["route"],
                state.get("tool_outputs", []),
                state.get("content_results", ()),
                state.get("citations", []),
            )
        }


def route_question(question: str) -> ChatRoute:
    normalized = question.casefold()
    quantitative = any(term in normalized for term in _QUANTITATIVE_TERMS)
    content = any(term in normalized for term in _CONTENT_TERMS)
    if quantitative and content:
        return "mixed"
    if quantitative:
        return "quantitative"
    return "content"


def _structured_request(question: str) -> StructuredQueryRequest:
    normalized = question.casefold()
    if any(term in normalized for term in ("waiting on", "overdue", "follow-up", "follow up")):
        return StructuredQueryRequest(template="live_applications")
    if "funnel" in normalized:
        return StructuredQueryRequest(template="funnel")
    if any(term in normalized for term in ("rate", "conversion")):
        return StructuredQueryRequest(template="rates")
    if "role" in normalized:
        return StructuredQueryRequest(template="breakdown", breakdown_dimension="role")
    return StructuredQueryRequest(template="summary_counts")


def synthesize_grounded_answer(
    route: ChatRoute,
    tool_outputs: list[ToolOutput],
    content_results: tuple[SemanticSearchResult, ...],
    citations: list[ChatCitation],
) -> str:
    parts: list[str] = []
    structured = next((item for item in tool_outputs if item["tool"] == "structured_query"), None)
    if structured is not None:
        rows = structured.get("rows")
        if isinstance(rows, list) and rows:
            if structured.get("template") == "live_applications":
                return _synthesize_live_applications(rows)
            rendered_rows = []
            for row in rows:
                if isinstance(row, dict):
                    rendered_rows.append(f"{row.get('label')}: {row.get('values')}")
            parts.append("Deterministic result: " + "; ".join(rendered_rows) + ".")
        else:
            parts.append("The deterministic query found no matching applications.")
    if content_results:
        excerpts = []
        email_citations = [item for item in citations if item.source == "email"]
        for result, citation in zip(content_results, email_citations, strict=True):
            excerpt = " ".join(result.content.split())[:280]
            excerpts.append(f'"{excerpt}" [{citation.citation_id}]')
        parts.append("Relevant source email evidence: " + " ".join(excerpts))
    elif route in {"content", "mixed"}:
        parts.append(
            "I cannot answer the email-content portion because no retained job-related "
            "source email was retrieved."
        )
    return " ".join(parts)


def _synthesize_live_applications(rows: list[object]) -> str:
    waiting: list[str] = []
    overdue: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        company = values.get("company")
        role = values.get("role_title")
        application_id = values.get("application_id")
        if not all(isinstance(value, str) for value in (company, role, application_id)):
            continue
        citation_id = f"application:{application_id}"
        label = f"{company} - {role} [{citation_id}]"
        waiting.append(label)
        if values.get("follow_up_due") is True:
            days_waiting = values.get("days_waiting")
            overdue.append(f"{label} ({days_waiting} days waiting)")

    if not waiting:
        return "The deterministic query found no applications awaiting an employer response."
    overdue_text = ", ".join(overdue) if overdue else "None"
    return f"Waiting on: {', '.join(waiting)}. Overdue for follow-up: {overdue_text}."


def _structured_citations(template: str, output: ToolOutput) -> list[ChatCitation]:
    if template == "live_applications":
        rows = output.get("rows")
        if isinstance(rows, list):
            result = []
            for row in rows:
                values = row.get("values") if isinstance(row, dict) else None
                application_id = values.get("application_id") if isinstance(values, dict) else None
                if isinstance(application_id, str):
                    result.append(
                        ChatCitation(
                            citation_id=f"application:{application_id}",
                            source="application",
                            application_id=application_id,
                        )
                    )
            return result
    return [
        ChatCitation(
            citation_id=f"metric:{template}",
            source="metric",
            metric_template=template,
        )
    ]
