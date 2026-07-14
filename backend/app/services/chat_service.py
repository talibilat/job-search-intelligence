from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.agent.tools import SemanticSearchTool, StructuredQueryRequest, StructuredQueryTool
from app.db.repositories import ChatRepository
from app.models import ChatCitation, ChatIncrement, ChatRequest, ChatResponse, ChatRoute
from app.models.chat import SemanticSearchResult
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
        self._index_service = index_service
        self._structured_query = structured_query
        self._semantic_search = semantic_search

    async def answer(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or uuid4().hex
        route = route_question(request.message)
        tool_outputs: list[dict[str, object]] = []
        citations: list[ChatCitation] = []
        content_results: tuple[SemanticSearchResult, ...] = ()

        if route in {"quantitative", "mixed"}:
            structured_result = self._structured_query.run(_structured_request(request.message))
            structured_output = structured_result.model_dump(mode="json")
            tool_outputs.append(structured_output)
            citations.extend(_structured_citations(structured_result.template, structured_output))
        if route in {"content", "mixed"}:
            await self._index_service.reconcile()
            content_results = await self._semantic_search.run(
                request.message,
                limit=request.retrieval_limit,
            )
            semantic_output: dict[str, object] = {
                "tool": "semantic_search",
                "results": [
                    item.model_dump(mode="json", exclude={"content"}) for item in content_results
                ],
            }
            tool_outputs.append(semantic_output)
            citations.extend(_semantic_citations(content_results))

        answer = synthesize_grounded_answer(route, tool_outputs, content_results, citations)
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
    tool_outputs: list[dict[str, object]],
    content_results: tuple[SemanticSearchResult, ...],
    citations: list[ChatCitation],
) -> str:
    parts: list[str] = []
    structured = next((item for item in tool_outputs if item["tool"] == "structured_query"), None)
    if structured is not None:
        rows = structured.get("rows")
        if isinstance(rows, list) and rows:
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


def _structured_citations(template: str, output: dict[str, object]) -> list[ChatCitation]:
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


def _semantic_citations(results: tuple[SemanticSearchResult, ...]) -> list[ChatCitation]:
    return [
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
