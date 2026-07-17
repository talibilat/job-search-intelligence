from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.agent.tools import SemanticSearchTool, StructuredQueryRequest, StructuredQueryTool
from app.models.application import (
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from app.models.chat import ChatCitation, ChatRequest, ChatRoute, SemanticSearchResult
from app.models.metrics import MetricsBreakdownDimension, MetricsFilter
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
_RELATIVE_WINDOW_TERMS = ("this week", "this month", "this year")
_TIMING_TERMS = (
    "average time",
    "how long does it take",
    "time to first response",
    "time-to-first-response",
    "time to rejection",
    "time-to-rejection",
)
_APPLICATION_TREND_TERMS = (
    "application volume",
    "applications trended",
    "applications over time",
)
_SOURCE_FILTER_TERMS: tuple[tuple[ApplicationSource, tuple[str, ...]], ...] = (
    ("linkedin", ("linkedin",)),
    ("company_site", ("company site", "company website", "careers page")),
    ("indeed", ("indeed",)),
    ("referral", ("referral", "referred")),
    ("other", ("other source",)),
)
_WORK_MODE_FILTER_TERMS: tuple[tuple[WorkMode, tuple[str, ...]], ...] = (
    ("remote", ("remote", "fully remote")),
    ("hybrid", ("hybrid",)),
    ("onsite", ("onsite", "on-site", "on site")),
)
_SPONSORSHIP_FILTER_TERMS: tuple[tuple[SponsorshipStatus, tuple[str, ...]], ...] = (
    (
        "not_offered",
        (
            "didn't offer sponsorship",
            "did not offer sponsorship",
            "not offered sponsorship",
            "without sponsorship",
            "no sponsorship",
        ),
    ),
    ("unknown", ("sponsorship unknown", "unknown sponsorship")),
    (
        "offered",
        (
            "offered sponsorship",
            "offers sponsorship",
            "offer sponsorship",
            "with sponsorship",
        ),
    ),
)
_STATUS_FILTER_TERMS: tuple[tuple[ApplicationStatus, tuple[str, ...]], ...] = (
    ("applied", ("at the applied stage", "current status is applied")),
    ("in_review", ("in review", "under review")),
    (
        "assessment",
        ("in the assessment stage", "at the assessment stage", "currently in assessment"),
    ),
    (
        "interview",
        ("currently interviewing", "in the interview stage", "at the interview stage"),
    ),
    ("offer", ("at the offer stage", "currently at offer stage")),
    ("rejected", ("rejected application", "currently rejected")),
    ("ghosted", ("ghosted application", "currently ghosted")),
    ("withdrawn", ("withdrawn application", "currently withdrawn")),
)
_SALARY_AMOUNT_PATTERN = r"(?:[$£€]\s*)?([0-9][0-9,]*(?:\.[0-9]+)?\s*[kK]?)"
_ROLE_ONLY_FILTER_VALUES = frozenset(
    {
        "hybrid",
        "on site",
        "on-site",
        "onsite",
        "remote",
    }
)
_BREAKDOWN_DIMENSION_TERMS: tuple[tuple[MetricsBreakdownDimension, tuple[str, ...]], ...] = (
    ("role", ("by role", "which role", "job title")),
    ("source", ("by source", "which source", "application source")),
    ("salary", ("by salary", "salary band")),
    ("company_type", ("company type",)),
    ("industry", ("by industry", "which industry")),
    ("tech", ("by tech", "tech stack", "which technolog", "which skill")),
    ("sponsorship", ("by sponsorship", "sponsorship vs")),
    ("seniority", ("by seniority", "seniority level")),
    ("work_mode", ("work mode", "remote vs", "hybrid vs", "onsite vs", "on-site vs")),
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
    quantitative = (
        any(term in normalized for term in _QUANTITATIVE_TERMS)
        or any(term in normalized for term in _RELATIVE_WINDOW_TERMS)
        or any(term in normalized for term in _TIMING_TERMS)
        or any(term in normalized for term in _APPLICATION_TREND_TERMS)
        or any(term in normalized for _, terms in _BREAKDOWN_DIMENSION_TERMS for term in terms)
        or len(_matched_sources(normalized)) > 1
    )
    content = any(term in normalized for term in _CONTENT_TERMS)
    if quantitative and content:
        return "mixed"
    if quantitative:
        return "quantitative"
    return "content"


def _structured_request(
    question: str,
    *,
    anchor_at: datetime | None = None,
) -> StructuredQueryRequest:
    normalized = question.casefold()
    filters = _structured_filters(normalized, anchor_at=anchor_at)
    if any(term in normalized for term in ("waiting on", "overdue", "follow-up", "follow up")):
        return StructuredQueryRequest(template="live_applications", filters=filters)
    if "funnel" in normalized:
        return StructuredQueryRequest(template="funnel", filters=filters)
    if any(term in normalized for term in _TIMING_TERMS):
        return StructuredQueryRequest(template="timing", filters=filters)
    if any(term in normalized for term in _APPLICATION_TREND_TERMS):
        return StructuredQueryRequest(template="application_timeseries", filters=filters)
    if len(_matched_sources(normalized)) > 1:
        return StructuredQueryRequest(
            template="breakdown",
            filters=filters,
            breakdown_dimension="source",
        )
    for dimension, terms in _BREAKDOWN_DIMENSION_TERMS:
        if any(term in normalized for term in terms):
            return StructuredQueryRequest(
                template="breakdown",
                filters=filters,
                breakdown_dimension=dimension,
            )
    if any(term in normalized for term in ("rate", "conversion")):
        return StructuredQueryRequest(template="rates", filters=filters)
    return StructuredQueryRequest(template="summary_counts", filters=filters)


def _structured_filters(
    normalized_question: str,
    *,
    anchor_at: datetime | None,
) -> MetricsFilter | None:
    filters = _relative_window_filter(normalized_question, anchor_at=anchor_at)
    if filters is None:
        filters = _calendar_year_filter(normalized_question)
    matched_sources = _matched_sources(normalized_question)
    source = next(iter(matched_sources)) if len(matched_sources) == 1 else None
    matched_work_modes = {
        work_mode
        for work_mode, terms in _WORK_MODE_FILTER_TERMS
        if any(term in normalized_question for term in terms)
    }
    work_mode = (
        next(iter(matched_work_modes))
        if len(matched_work_modes) == 1
        and not any(
            term in normalized_question
            for dimension, terms in _BREAKDOWN_DIMENSION_TERMS
            if dimension == "work_mode"
            for term in terms
        )
        else None
    )
    sponsorship = next(
        (
            sponsorship
            for sponsorship, terms in _SPONSORSHIP_FILTER_TERMS
            if any(term in normalized_question for term in terms)
        ),
        None,
    )
    if any(
        term in normalized_question
        for dimension, terms in _BREAKDOWN_DIMENSION_TERMS
        if dimension == "sponsorship"
        for term in terms
    ):
        sponsorship = None
    matched_statuses = {
        status
        for status, terms in _STATUS_FILTER_TERMS
        if any(term in normalized_question for term in terms)
    }
    status = next(iter(matched_statuses)) if len(matched_statuses) == 1 else None
    role = _role_filter(normalized_question)
    salary_min, salary_max = _salary_filter(normalized_question)
    updates = {
        key: value
        for key, value in (
            ("source", source),
            ("sponsorship", sponsorship),
            ("status", status),
            ("role", role),
            ("work_mode", work_mode),
            ("salary_min", salary_min),
            ("salary_max", salary_max),
        )
        if value is not None
    }
    if not updates:
        return filters
    if filters is None:
        return MetricsFilter.model_validate(updates)
    return filters.model_copy(update=updates)


def _matched_sources(normalized_question: str) -> set[ApplicationSource]:
    return {
        source
        for source, terms in _SOURCE_FILTER_TERMS
        if any(term in normalized_question for term in terms)
    }


def _role_filter(normalized_question: str) -> str | None:
    quoted_match = re.search(
        r"\b(?:role|job title)\s+(?:is\s+)?(['\"])([^'\"]{1,100})\1",
        normalized_question,
    )
    if quoted_match is not None:
        return quoted_match.group(2).strip()

    role_match = re.search(
        r"\bapplications?\s+for\s+(?:an?\s+)?(.{1,100}?)\s+"
        r"(?:roles?|positions?|jobs?)\b",
        normalized_question,
    )
    if role_match is None:
        return None
    role = role_match.group(1).strip()
    if role in _ROLE_ONLY_FILTER_VALUES:
        return None
    return role


def _salary_filter(normalized_question: str) -> tuple[int | None, int | None]:
    if "salary" not in normalized_question:
        return None, None

    range_match = re.search(
        rf"salary(?:\s+(?:is|of))?\s+(?:between\s+)?{_SALARY_AMOUNT_PATTERN}"
        rf"\s*(?:-|to|and)\s*{_SALARY_AMOUNT_PATTERN}",
        normalized_question,
    )
    if range_match is not None:
        lower = _parse_salary_amount(range_match.group(1))
        upper = _parse_salary_amount(range_match.group(2))
        if lower <= upper:
            return lower, upper
        return None, None

    minimum_match = re.search(
        rf"salary\s+(?:of\s+)?(?:at least|over|above|from)\s+{_SALARY_AMOUNT_PATTERN}",
        normalized_question,
    )
    if minimum_match is not None:
        return _parse_salary_amount(minimum_match.group(1)), None

    maximum_match = re.search(
        rf"salary\s+(?:of\s+)?(?:at most|under|below|up to)\s+{_SALARY_AMOUNT_PATTERN}",
        normalized_question,
    )
    if maximum_match is not None:
        return None, _parse_salary_amount(maximum_match.group(1))
    return None, None


def _parse_salary_amount(value: str) -> int:
    normalized = value.replace(",", "").replace(" ", "")
    multiplier = 1_000 if normalized.endswith("k") else 1
    if multiplier != 1:
        normalized = normalized[:-1]
    return int(float(normalized) * multiplier)


def _relative_window_filter(
    normalized_question: str,
    *,
    anchor_at: datetime | None,
) -> MetricsFilter | None:
    if not any(term in normalized_question for term in _RELATIVE_WINDOW_TERMS):
        return None

    anchor = (anchor_at or datetime.now(UTC)).astimezone(UTC)
    if "this week" in normalized_question:
        start = (anchor - timedelta(days=anchor.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        next_period = start + timedelta(days=7)
    elif "this month" in normalized_question:
        start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            next_period = start.replace(year=start.year + 1, month=1)
        else:
            next_period = start.replace(month=start.month + 1)
    else:
        start = anchor.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        next_period = start.replace(year=start.year + 1)

    return MetricsFilter(
        first_seen_from=start,
        first_seen_to=next_period - timedelta(microseconds=1),
    )


def _calendar_year_filter(normalized_question: str) -> MetricsFilter | None:
    match = re.search(r"\b(?:in|during)\s+((?:19|20)\d{2})\b", normalized_question)
    if match is None:
        return None

    year = int(match.group(1))
    start = datetime(year, 1, 1, tzinfo=UTC)
    next_year = start.replace(year=year + 1)
    return MetricsFilter(
        first_seen_from=start,
        first_seen_to=next_year - timedelta(microseconds=1),
    )


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
        if all(result.company is not None for result in content_results):
            email_citations = [item for item in citations if item.source == "email"]
            companies = [
                f"{result.company} [{citation.citation_id}]"
                for result, citation in zip(content_results, email_citations, strict=True)
            ]
            parts.append("Companies mentioning the requested term: " + ", ".join(companies) + ".")
            return " ".join(parts)
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
