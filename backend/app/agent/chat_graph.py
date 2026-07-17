from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.agent.tools import (
    CachedInsightTool,
    SemanticSearchTool,
    StructuredQueryRequest,
    StructuredQueryTool,
)
from app.models.application import (
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from app.models.chat import ChatCitation, ChatRequest, ChatRoute, SemanticSearchResult
from app.models.insight import InsightType
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
_GHOST_THRESHOLD_TERMS = (
    "ghost threshold",
    "days of silence",
    "effectively dead",
)
_APPLICATION_TREND_TERMS = (
    "application volume",
    "applications trended",
    "applications over time",
)
_RESPONSE_RATE_TREND_TERMS = (
    "response rate improving",
    "response rate trend",
    "response rate over time",
)
_SUCCESSFUL_APPLICATION_TRAIT_TERMS = (
    "successful application",
    "successful applications",
    "wins have in common",
)
_NEGATIVE_OUTCOME_TRAIT_TERMS = (
    "rejected/ghosted application",
    "rejected or ghosted application",
    "rejected and ghosted application",
    "negative outcomes have in common",
)
_STRONGEST_RESPONSE_CORRELATE_TERMS = (
    "strongest response correlate",
    "single factor correlates most",
    "correlates most with getting a response",
    "most correlated with response",
)
_WASTED_EFFORT_TERMS = (
    "wasted effort",
    "pouring effort",
    "never converts",
    "never convert",
    "lowest conversion",
)
_BEST_ROI_SOURCE_TERMS = (
    "best roi source",
    "source gives the best roi",
    "best source for interviews",
    "most interviews per application",
)
_SPONSORSHIP_RESPONSE_IMPACT_TERMS = (
    "sponsorship requirement measurably hurting",
    "sponsorship requirement hurting",
    "sponsorship hurting my response rate",
    "sponsorship hurt my response rate",
    "response rate impact of sponsorship",
    "sponsorship response impact",
)
_SKILL_SIGNAL_TERMS = (
    "skills actually sell",
    "skills that sell",
    "skill signals",
    "dead-weight skill",
    "dead weight skill",
    "skills correlate with interviews",
)
_ADJACENT_ROLE_TERMS = (
    "adjacent role",
    "roles i don't apply to",
    "roles i do not apply to",
    "roles should i explore",
    "roles should i consider",
)
_WHY_REJECTED_INSIGHT_TERMS = (
    "why am i getting rejected",
    "why do i keep getting rejected",
    "why i am getting rejected",
    "recurring themes across rejection",
    "rejection themes",
)
_RECURRING_FEEDBACK_INSIGHT_TERMS = (
    "feedback consistently say",
    "feedback says i should improve",
    "feedback say i should improve",
    "feedback says i need to improve",
    "feedback say i need to improve",
    "recurring feedback",
    "consistent feedback",
)
_SKILL_GAPS_INSIGHT_TERMS = (
    "skills keep appearing in roles i get rejected from",
    "technologies keep appearing in roles i get rejected from",
    "real skill gaps",
    "skill gaps",
)
_STRONGEST_WEAKEST_SIGNALS_INSIGHT_TERMS = (
    "strongest and weakest signals",
    "strongest & weakest signals",
    "strongest/weakest signals",
)
_ROLE_FIT_INSIGHT_TERMS = (
    "roles genuinely suit me best",
    "roles suit me best",
    "best-fit roles",
    "best fit roles",
    "pattern of my wins",
)
_WEEKLY_ACTIONS_INSIGHT_TERMS = (
    "3 concrete things i should do next week",
    "three concrete things i should do next week",
    "what should i do next week",
    "actions should i take next week",
    "next-week actions",
    "weekly actions",
)
_STORY_INSIGHT_TERMS = (
    "story my last 6-12 months of job searching tells",
    "story my last 6 to 12 months of job searching tells",
    "job search story",
    "story of my job search",
    "search story",
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
type ToolBranch = Literal["quantitative", "content", "mixed", "cached_insight"]


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
        cached_insight: CachedInsightTool,
    ) -> None:
        self._index_service = index_service
        self._structured_query = structured_query
        self._semantic_search = semantic_search
        self._cached_insight = cached_insight

        builder = StateGraph(ChatGraphState)
        builder.add_node("route", self._route)
        builder.add_node("structured_query", self._run_structured_query)
        builder.add_node("semantic_search", self._run_semantic_search)
        builder.add_node("cached_insight", self._run_cached_insight)
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
                "cached_insight": "cached_insight",
            },
        )
        builder.add_edge("structured_query", "synthesize")
        builder.add_edge("semantic_search", "synthesize")
        builder.add_edge("cached_insight", "synthesize")
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
        if _cached_insight_type(state["request"].message) is not None:
            return "cached_insight"
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

    def _run_cached_insight(self, state: ChatGraphState) -> ChatGraphState:
        insight_type = _cached_insight_type(state["request"].message)
        if insight_type is None:  # pragma: no cover - guarded by the graph branch
            raise RuntimeError("Cached insight node received an unsupported question.")
        result = self._cached_insight.run(insight_type)
        citations = [
            ChatCitation(
                citation_id=item.citation_id,
                source="email" if item.email_public_id is not None else "application",
                email_public_id=item.email_public_id,
                application_id=item.application_id,
                subject=item.email_subject,
            )
            for item in result.citations
        ]
        return {
            "tool_outputs": [result.model_dump(mode="json")],
            "citations": citations,
            "content_results": (),
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
    if _cached_insight_type(question) is not None:
        return "content"
    normalized = question.casefold()
    quantitative = (
        any(term in normalized for term in _QUANTITATIVE_TERMS)
        or any(term in normalized for term in _RELATIVE_WINDOW_TERMS)
        or any(term in normalized for term in _TIMING_TERMS)
        or any(term in normalized for term in _GHOST_THRESHOLD_TERMS)
        or any(term in normalized for term in _APPLICATION_TREND_TERMS)
        or any(term in normalized for term in _RESPONSE_RATE_TREND_TERMS)
        or _asks_successful_application_traits(normalized)
        or _asks_negative_outcome_traits(normalized)
        or _asks_strongest_response_correlate(normalized)
        or _asks_wasted_effort_segments(normalized)
        or _asks_best_roi_source(normalized)
        or _asks_sponsorship_response_impact(normalized)
        or _asks_skill_signals(normalized)
        or _asks_adjacent_roles(normalized)
        or any(term in normalized for _, terms in _BREAKDOWN_DIMENSION_TERMS for term in terms)
        or len(_matched_sources(normalized)) > 1
    )
    content = any(term in normalized for term in _CONTENT_TERMS)
    if quantitative and content:
        return "mixed"
    if quantitative:
        return "quantitative"
    return "content"


def _cached_insight_type(question: str) -> InsightType | None:
    normalized = question.casefold()
    if any(term in normalized for term in _WEEKLY_ACTIONS_INSIGHT_TERMS):
        return "weekly_actions"
    if any(term in normalized for term in _WHY_REJECTED_INSIGHT_TERMS):
        return "why_rejected"
    if any(term in normalized for term in _RECURRING_FEEDBACK_INSIGHT_TERMS):
        return "recurring_feedback"
    if any(term in normalized for term in _SKILL_GAPS_INSIGHT_TERMS):
        return "skill_gaps"
    if any(term in normalized for term in _STRONGEST_WEAKEST_SIGNALS_INSIGHT_TERMS):
        return "strongest_weakest_signals"
    if any(term in normalized for term in _ROLE_FIT_INSIGHT_TERMS):
        return "role_fit"
    if any(term in normalized for term in _STORY_INSIGHT_TERMS):
        return "story"
    return None


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
    if any(term in normalized for term in _GHOST_THRESHOLD_TERMS):
        return StructuredQueryRequest(template="personal_ghost_threshold", filters=filters)
    if any(term in normalized for term in _RESPONSE_RATE_TREND_TERMS):
        return StructuredQueryRequest(template="response_rate_timeseries", filters=filters)
    if _asks_successful_application_traits(normalized):
        return StructuredQueryRequest(template="successful_application_segments", filters=filters)
    if _asks_negative_outcome_traits(normalized):
        if filters is not None and filters.status in {"rejected", "ghosted"}:
            filters = filters.model_copy(update={"status": None})
        return StructuredQueryRequest(template="negative_outcome_segments", filters=filters)
    if _asks_strongest_response_correlate(normalized):
        return StructuredQueryRequest(template="strongest_response_correlate", filters=filters)
    if _asks_wasted_effort_segments(normalized):
        return StructuredQueryRequest(template="wasted_effort_segments", filters=filters)
    if _asks_best_roi_source(normalized):
        return StructuredQueryRequest(template="best_roi_source", filters=filters)
    if _asks_sponsorship_response_impact(normalized):
        if filters is not None and filters.sponsorship is not None:
            filters = filters.model_copy(update={"sponsorship": None})
        return StructuredQueryRequest(template="sponsorship_response_impact", filters=filters)
    if _asks_skill_signals(normalized):
        return StructuredQueryRequest(template="skill_signal_segments", filters=filters)
    if _asks_adjacent_roles(normalized):
        return StructuredQueryRequest(template="adjacent_role_suggestions", filters=filters)
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


def _asks_successful_application_traits(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _SUCCESSFUL_APPLICATION_TRAIT_TERMS) or (
        "successful" in normalized_question
        and "application" in normalized_question
        and "in common" in normalized_question
    )


def _asks_negative_outcome_traits(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _NEGATIVE_OUTCOME_TRAIT_TERMS) or (
        "application" in normalized_question
        and "in common" in normalized_question
        and "rejected" in normalized_question
        and "ghosted" in normalized_question
    )


def _asks_strongest_response_correlate(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _STRONGEST_RESPONSE_CORRELATE_TERMS)


def _asks_wasted_effort_segments(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _WASTED_EFFORT_TERMS)


def _asks_best_roi_source(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _BEST_ROI_SOURCE_TERMS)


def _asks_sponsorship_response_impact(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _SPONSORSHIP_RESPONSE_IMPACT_TERMS)


def _asks_skill_signals(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _SKILL_SIGNAL_TERMS) or (
        "skill" in normalized_question
        and (
            "sell" in normalized_question
            or "dead weight" in normalized_question
            or ("correlate" in normalized_question and "interview" in normalized_question)
        )
    )


def _asks_adjacent_roles(normalized_question: str) -> bool:
    return any(term in normalized_question for term in _ADJACENT_ROLE_TERMS)


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
    cached_insight = next(
        (item for item in tool_outputs if item["tool"] == "cached_insight"),
        None,
    )
    if cached_insight is not None:
        status = cached_insight.get("status")
        content = cached_insight.get("content")
        if status == "available" and isinstance(content, str):
            return content
        insight_type = cached_insight.get("insight_type")
        if insight_type == "recurring_feedback":
            insight_label = "recurring-feedback"
        elif insight_type == "skill_gaps":
            insight_label = "skill-gaps"
        elif insight_type == "strongest_weakest_signals":
            insight_label = "strongest-and-weakest-signals"
        elif insight_type == "role_fit":
            insight_label = "role-fit"
        elif insight_type == "weekly_actions":
            insight_label = "weekly-actions"
        elif insight_type == "story":
            insight_label = "search-story"
        else:
            insight_label = "rejection-themes"
        if status == "stale":
            return (
                f"The cached {insight_label} insight is stale because its source data changed. "
                "Regenerate it on the Insights page before relying on it here."
            )
        return (
            f"The {insight_label} insight has not been generated yet. Generate it on the "
            "Insights page, then ask again."
        )
    structured = next((item for item in tool_outputs if item["tool"] == "structured_query"), None)
    if structured is not None:
        rows = structured.get("rows")
        if structured.get("template") == "successful_application_segments" and isinstance(
            rows, list
        ):
            parts.append(_synthesize_successful_application_segments(rows))
        elif structured.get("template") == "negative_outcome_segments" and isinstance(rows, list):
            parts.append(_synthesize_negative_outcome_segments(rows))
        elif structured.get("template") == "strongest_response_correlate" and isinstance(
            rows, list
        ):
            parts.append(_synthesize_strongest_response_correlate(rows))
        elif structured.get("template") == "wasted_effort_segments" and isinstance(rows, list):
            parts.append(_synthesize_wasted_effort_segments(rows))
        elif structured.get("template") == "best_roi_source" and isinstance(rows, list):
            parts.append(_synthesize_best_roi_source(rows))
        elif structured.get("template") == "sponsorship_response_impact" and isinstance(rows, list):
            parts.append(_synthesize_sponsorship_response_impact(rows))
        elif structured.get("template") == "skill_signal_segments" and isinstance(rows, list):
            parts.append(_synthesize_skill_signal_segments(rows))
        elif structured.get("template") == "adjacent_role_suggestions" and isinstance(rows, list):
            parts.append(_synthesize_adjacent_role_suggestions(rows))
        elif isinstance(rows, list) and rows:
            if structured.get("template") == "live_applications":
                parts.append(_synthesize_live_applications(rows))
            else:
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


def _synthesize_successful_application_segments(rows: list[object]) -> str:
    segments: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        dimension = values.get("dimension")
        value = values.get("value")
        success_count = values.get("success_count")
        application_count = values.get("application_count")
        success_rate = values.get("success_rate")
        success_rate_lift = values.get("success_rate_lift")
        if (
            not isinstance(dimension, str)
            or not isinstance(value, str)
            or not isinstance(success_count, int)
            or not isinstance(application_count, int)
            or not isinstance(success_rate, (int, float))
            or not isinstance(success_rate_lift, (int, float))
        ):
            continue
        segments.append(
            f"{dimension} {value}: {success_count} of {application_count} "
            f"({success_rate:.1%}), {success_rate_lift:.1%} above the filtered baseline"
        )

    if not segments:
        return (
            "No segment has a success rate above the filtered baseline, so there is not "
            "enough deterministic evidence to identify a shared successful-application trait."
        )
    return (
        "Success means an application with interview or offer evidence. The strongest "
        "above-baseline associations are: "
        + "; ".join(segments)
        + ". These are correlations, not proof that a segment caused success."
    )


def _synthesize_negative_outcome_segments(rows: list[object]) -> str:
    segments: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        dimension = values.get("dimension")
        value = values.get("value")
        negative_count = values.get("negative_count")
        application_count = values.get("application_count")
        negative_rate = values.get("negative_rate")
        negative_rate_lift = values.get("negative_rate_lift")
        if (
            not isinstance(dimension, str)
            or not isinstance(value, str)
            or not isinstance(negative_count, int)
            or not isinstance(application_count, int)
            or not isinstance(negative_rate, (int, float))
            or not isinstance(negative_rate_lift, (int, float))
        ):
            continue
        segments.append(
            f"{dimension} {value}: {negative_count} of {application_count} "
            f"({negative_rate:.1%}), {negative_rate_lift:.1%} above the filtered baseline"
        )

    if not segments:
        return (
            "No segment has a rejected-or-ghosted rate above the filtered baseline, so there "
            "is not enough deterministic evidence to identify a shared negative-outcome trait."
        )
    return (
        "A negative outcome means an application currently marked rejected or ghosted. The "
        "strongest above-baseline associations are: "
        + "; ".join(segments)
        + ". These are correlations, not proof that a segment caused the negative outcome."
    )


def _synthesize_strongest_response_correlate(rows: list[object]) -> str:
    if not rows:
        return (
            "No segment has a response rate above the filtered baseline, so there is not "
            "enough deterministic evidence to identify a strongest response correlate."
        )
    row = rows[0]
    values = row.get("values") if isinstance(row, dict) else None
    if not isinstance(values, dict):
        return "There is not enough deterministic evidence to identify a response correlate."
    dimension = values.get("dimension")
    value = values.get("value")
    response_count = values.get("response_count")
    application_count = values.get("application_count")
    response_rate = values.get("response_rate")
    response_rate_lift = values.get("response_rate_lift")
    if (
        not isinstance(dimension, str)
        or not isinstance(value, str)
        or not isinstance(response_count, int)
        or not isinstance(application_count, int)
        or not isinstance(response_rate, (int, float))
        or not isinstance(response_rate_lift, (int, float))
    ):
        return "There is not enough deterministic evidence to identify a response correlate."
    return (
        f"The strongest response correlate is {dimension} {value}: {response_count} of "
        f"{application_count} applications received a response ({response_rate:.1%}), "
        f"{response_rate_lift:.1%} above the filtered baseline. This is a correlation, "
        "not proof that the factor caused the response."
    )


def _synthesize_wasted_effort_segments(rows: list[object]) -> str:
    segments: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        dimension = values.get("dimension")
        value = values.get("value")
        response_count = values.get("response_count")
        application_count = values.get("application_count")
        response_rate = values.get("response_rate")
        response_rate_lift = values.get("response_rate_lift")
        if (
            not isinstance(dimension, str)
            or not isinstance(value, str)
            or not isinstance(response_count, int)
            or not isinstance(application_count, int)
            or not isinstance(response_rate, (int, float))
            or not isinstance(response_rate_lift, (int, float))
        ):
            continue
        segments.append(
            f"{dimension} {value}: {response_count} of {application_count} responses "
            f"({response_rate:.1%}), {abs(response_rate_lift):.1%} below the filtered baseline"
        )

    if not segments:
        return (
            "No segment has a response rate below the filtered baseline, so there is not "
            "enough deterministic evidence to identify wasted-effort segments."
        )
    return (
        "The strongest below-baseline response associations are: "
        + "; ".join(segments)
        + ". These are correlations, not proof that effort in a segment caused the lower "
        "response rate."
    )


def _synthesize_best_roi_source(rows: list[object]) -> str:
    if not rows:
        return (
            "There is not enough deterministic evidence to identify a best-ROI application "
            "source with interview data."
        )
    row = rows[0]
    values = row.get("values") if isinstance(row, dict) else None
    if not isinstance(values, dict):
        return "There is not enough deterministic evidence to identify a best-ROI source."
    source = values.get("source")
    interview_count = values.get("interview_count")
    application_count = values.get("application_count")
    interview_rate = values.get("interview_rate")
    if (
        not isinstance(source, str)
        or not isinstance(interview_count, int)
        or not isinstance(application_count, int)
        or not isinstance(interview_rate, (int, float))
    ):
        return "There is not enough deterministic evidence to identify a best-ROI source."
    return (
        f"The best-ROI application source is {source}: {interview_count} of "
        f"{application_count} applications reached an interview ({interview_rate:.1%}). "
        "ROI here means interviews per application, not financial return."
    )


def _synthesize_sponsorship_response_impact(rows: list[object]) -> str:
    if not rows:
        return (
            "There is not enough deterministic evidence to measure sponsorship's impact "
            "on response rate."
        )
    row = rows[0]
    values = row.get("values") if isinstance(row, dict) else None
    if not isinstance(values, dict):
        return "There is not enough deterministic evidence to measure sponsorship impact."
    sponsorship = values.get("sponsorship")
    response_count = values.get("response_count")
    application_count = values.get("application_count")
    response_rate = values.get("response_rate")
    response_rate_lift = values.get("response_rate_lift")
    baseline_response_rate = values.get("baseline_response_rate")
    if (
        not isinstance(sponsorship, str)
        or not isinstance(response_count, int)
        or not isinstance(application_count, int)
        or not isinstance(response_rate, (int, float))
        or not isinstance(response_rate_lift, (int, float))
        or not isinstance(baseline_response_rate, (int, float))
    ):
        return "There is not enough deterministic evidence to measure sponsorship impact."
    direction = "below" if response_rate_lift < 0 else "above"
    conclusion = (
        "This is associated with a lower response rate."
        if response_rate_lift < 0
        else "This does not show a lower response rate."
    )
    return (
        f"For sponsorship status {sponsorship}, {response_count} of {application_count} "
        f"applications received a response ({response_rate:.1%}), "
        f"{abs(response_rate_lift):.1%} {direction} the filtered baseline of "
        f"{baseline_response_rate:.1%}. {conclusion} This is a correlation, not proof that "
        "sponsorship caused the difference."
    )


def _synthesize_skill_signal_segments(rows: list[object]) -> str:
    selling: list[str] = []
    dead_weight: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        signal = values.get("signal")
        skill = values.get("skill")
        application_count = values.get("application_count")
        interview_count = values.get("interview_count")
        interview_rate = values.get("interview_rate")
        response_count = values.get("response_count")
        response_rate = values.get("response_rate")
        response_rate_lift = values.get("response_rate_lift")
        if (
            not isinstance(signal, str)
            or not isinstance(skill, str)
            or not isinstance(application_count, int)
            or not isinstance(interview_count, int)
            or not isinstance(interview_rate, (int, float))
            or not isinstance(response_count, int)
            or not isinstance(response_rate, (int, float))
            or not isinstance(response_rate_lift, (int, float))
        ):
            continue
        if signal == "selling":
            selling.append(
                f"{skill}: {interview_count} of {application_count} reached interview "
                f"({interview_rate:.1%})"
            )
        elif signal == "dead_weight":
            dead_weight.append(
                f"{skill}: {response_count} of {application_count} received a response "
                f"({response_rate:.1%}), {abs(response_rate_lift):.1%} below the filtered baseline"
            )

    if not selling and not dead_weight:
        return (
            "There is not enough deterministic skill evidence to identify selling or "
            "dead-weight skills."
        )
    selling_text = "; ".join(selling) if selling else "Not enough interview evidence"
    dead_weight_text = "; ".join(dead_weight) if dead_weight else "None below response baseline"
    return (
        f"Skills that sell by interview rate: {selling_text}. Dead-weight skills by "
        f"below-baseline response rate: {dead_weight_text}. These are associations across "
        "technologies extracted from tracked applications, not proof that a skill caused "
        "an outcome."
    )


def _synthesize_adjacent_role_suggestions(rows: list[object]) -> str:
    suggestions: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        role = values.get("role")
        success_count = values.get("success_count")
        application_count = values.get("application_count")
        success_rate = values.get("success_rate")
        if (
            not isinstance(role, str)
            or not isinstance(success_count, int)
            or not isinstance(application_count, int)
            or not isinstance(success_rate, (int, float))
        ):
            continue
        suggestions.append(
            f"{role}: {success_count} of {application_count} reached interview or offer "
            f"({success_rate:.1%})"
        )

    if not suggestions:
        return (
            "There is not enough deterministic success evidence to identify role signals "
            "worth exploring."
        )
    return (
        "Tracked role signals worth exploring based on interview or offer evidence are: "
        + "; ".join(suggestions)
        + ". These are historical associations. The current data ranks roles already present "
        "in tracked applications; it cannot prove that a role is untried or semantically adjacent."
    )


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
