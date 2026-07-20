from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict, cast
from urllib.parse import urlparse

from langgraph.graph import END, START, StateGraph

from app.agent.planner import ChatPlan, ChatPlanner
from app.agent.tools import (
    CachedInsightTool,
    DateWindowSpec,
    SemanticSearchTool,
    StructuredQueryRequest,
    StructuredQueryTool,
    WebSearchTool,
)
from app.models.application import (
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from app.models.chat import (
    ChatCitation,
    ChatMessageRecord,
    ChatRequest,
    ChatRoute,
    SemanticSearchResult,
)
from app.models.insight import InsightType
from app.models.metrics import MetricsBreakdownDimension, MetricsFilter
from app.models.web_search import WebSearchRequest, WebSearchResult
from app.providers.llm import LLMProviderResponseError
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
    "which companies",
    "what companies",
    "list companies",
    "which month",
    "busiest month",
    "most applications",
    "list applications",
    "latest application",
    "most recent application",
    "last application",
)
_EXPLICIT_QUANTITATIVE_TERMS = (
    "how many",
    "count",
    "rate",
    "funnel",
    "conversion",
    "waiting on",
    "overdue",
    "follow-up",
    "follow up",
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
_EXCERPT_STOP_WORDS = frozenset(
    {
        "about",
        "did",
        "email",
        "exactly",
        "last",
        "mentioned",
        "recruiter",
        "said",
        "say",
        "their",
        "what",
    }
)
_RELATIVE_WINDOW_TERMS = (
    "this week",
    "last week",
    "this month",
    "last month",
    "this year",
    "last year",
    "past 7 days",
    "last 7 days",
)
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
type ToolBranch = Literal[
    "conversation",
    "quantitative",
    "content",
    "web",
    "mixed",
    "cached_insight",
    "mixed_cached_insight",
]


class ChatGraphState(TypedDict, total=False):
    request: ChatRequest
    history: tuple[ChatMessageRecord, ...]
    plan: ChatPlan
    route: ChatRoute
    tool_outputs: list[ToolOutput]
    citations: list[ChatCitation]
    content_results: tuple[SemanticSearchResult, ...]
    web_results: tuple[WebSearchResult, ...]
    answer: str


class ChatGraph:
    """Typed LangGraph orchestration over constrained local chat tools."""

    def __init__(
        self,
        *,
        planner: ChatPlanner,
        index_service: ChatIndexService,
        structured_query: StructuredQueryTool,
        semantic_search: SemanticSearchTool,
        cached_insight: CachedInsightTool,
        web_search: WebSearchTool,
    ) -> None:
        self._planner = planner
        self._index_service = index_service
        self._structured_query = structured_query
        self._semantic_search = semantic_search
        self._cached_insight = cached_insight
        self._web_search = web_search

        builder = StateGraph(ChatGraphState)
        builder.add_node("route", self._route)
        builder.add_node("structured_query", self._run_structured_query)
        builder.add_node("semantic_search", self._run_semantic_search)
        builder.add_node("cached_insight", self._run_cached_insight)
        builder.add_node("mixed_tools", self._run_mixed_tools)
        builder.add_node("mixed_cached_insight", self._run_mixed_cached_insight)
        builder.add_node("conversation", self._run_conversation)
        builder.add_node("web_search", self._run_web_search)
        builder.add_edge(START, "route")
        builder.add_conditional_edges(
            "route",
            self._tool_branch,
            {
                "quantitative": "structured_query",
                "content": "semantic_search",
                "mixed": "mixed_tools",
                "cached_insight": "cached_insight",
                "mixed_cached_insight": "mixed_cached_insight",
                "conversation": "conversation",
                "web": "web_search",
            },
        )
        builder.add_edge("structured_query", END)
        builder.add_edge("semantic_search", END)
        builder.add_edge("cached_insight", END)
        builder.add_edge("mixed_tools", END)
        builder.add_edge("mixed_cached_insight", END)
        builder.add_edge("conversation", END)
        builder.add_edge("web_search", END)
        self._graph = builder.compile()

    async def run(
        self,
        request: ChatRequest,
        *,
        history: tuple[ChatMessageRecord, ...] = (),
    ) -> ChatGraphState:
        result = await self._graph.ainvoke({"request": request, "history": history})
        return cast(ChatGraphState, result)

    async def stream(
        self,
        request: ChatRequest,
        *,
        history: tuple[ChatMessageRecord, ...] = (),
    ) -> AsyncIterator[tuple[str, ChatGraphState]]:
        async for update in self._graph.astream(
            {"request": request, "history": history},
            stream_mode="updates",
        ):
            for node, state_update in update.items():
                yield node, cast(ChatGraphState, state_update)

    async def _route(self, state: ChatGraphState) -> ChatGraphState:
        question = state["request"].message
        plan = await self._planner.plan(
            question,
            state.get("history", ()),
            timezone=state["request"].timezone,
        )
        if plan.route == "conversation" and _requires_web_search(question):
            plan = ChatPlan(
                route="web",
                web_search=WebSearchRequest(query=question, max_results=5),
            )
        deterministic_route = route_question(question)
        if deterministic_route == "quantitative" and plan.route not in {"conversation", "web"}:
            trusted_query = _structured_request(question)
            if plan.structured_query is not None:
                trusted_query = trusted_query.model_copy(
                    update={
                        "date_window": (
                            plan.structured_query.date_window or trusted_query.date_window
                        ),
                        "timezone": state["request"].timezone,
                    }
                )
            plan = ChatPlan(
                route="quantitative",
                structured_query=trusted_query,
            )
        elif deterministic_route == "mixed" and plan.route not in {"conversation", "web"}:
            if (
                plan.retrieval is None
                and plan.cached_insight_type is None
                and plan.web_search is None
            ):
                raise LLMProviderResponseError(
                    public_message="The AI planner omitted the content tool for a mixed question."
                )
            plan = ChatPlan(
                route="mixed",
                structured_query=_structured_request(question),
                retrieval=plan.retrieval,
                cached_insight_type=plan.cached_insight_type,
                web_search=plan.web_search,
            )
        return {"route": plan.route, "plan": plan}

    def _tool_branch(self, state: ChatGraphState) -> ToolBranch:
        if state["route"] == "mixed":
            return "mixed"
        if state["plan"].cached_insight_type is not None:
            return "cached_insight"
        return state["route"]

    def _run_conversation(self, state: ChatGraphState) -> ChatGraphState:
        return {"tool_outputs": [], "citations": [], "content_results": (), "web_results": ()}

    async def _run_web_search(self, state: ChatGraphState) -> ChatGraphState:
        request = state["plan"].web_search
        if request is None:  # pragma: no cover - guarded by ChatPlan
            raise RuntimeError("web plan is missing web_search")
        response = await self._web_search.run(request)
        citations = [
            ChatCitation(
                citation_id=f"web:{index}",
                source="web",
                web_title=result.title,
                web_url=str(result.url),
                web_domain=urlparse(str(result.url)).netloc,
                snippet=result.snippet,
            )
            for index, result in enumerate(response.results, 1)
        ]
        return {
            "tool_outputs": [
                {
                    "tool": "web_search",
                    "results": [item.model_dump(mode="json") for item in response.results],
                }
            ],
            "citations": citations,
            "content_results": (),
            "web_results": response.results,
        }

    def _run_structured_query(self, state: ChatGraphState) -> ChatGraphState:
        output, citations = self._structured_result(state["plan"])
        return {"tool_outputs": [output], "citations": citations, "content_results": ()}

    async def _run_semantic_search(self, state: ChatGraphState) -> ChatGraphState:
        results, output, citations = await self._semantic_result(state["request"], state["plan"])
        return {
            "tool_outputs": [output],
            "citations": citations,
            "content_results": results,
        }

    def _run_cached_insight(self, state: ChatGraphState) -> ChatGraphState:
        insight_type = state["plan"].cached_insight_type
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
                company=item.company,
                role_title=item.role_title,
                first_seen_at=item.event_at,
            )
            for item in result.citations
        ]
        return {
            "tool_outputs": [result.model_dump(mode="json")],
            "citations": citations,
            "content_results": (),
        }

    async def _run_mixed_tools(self, state: ChatGraphState) -> ChatGraphState:
        plan = state["plan"]
        outputs: list[ToolOutput] = []
        citations: list[ChatCitation] = []
        content_results: tuple[SemanticSearchResult, ...] = ()
        web_results: tuple[WebSearchResult, ...] = ()
        if plan.structured_query is not None:
            output, items = self._structured_result(plan)
            outputs.append(output)
            citations.extend(items)
        if plan.retrieval is not None:
            content_results, output, items = await self._semantic_result(state["request"], plan)
            outputs.append(output)
            citations.extend(items)
        if plan.cached_insight_type is not None:
            cached = self._run_cached_insight(state)
            outputs.extend(cached["tool_outputs"])
            citations.extend(cached["citations"])
        if plan.web_search is not None:
            web = await self._run_web_search(state)
            outputs.extend(web["tool_outputs"])
            citations.extend(web["citations"])
            web_results = web["web_results"]
        return {
            "tool_outputs": outputs,
            "citations": citations,
            "content_results": content_results,
            "web_results": web_results,
        }

    def _run_mixed_cached_insight(self, state: ChatGraphState) -> ChatGraphState:
        structured_output, structured_citations = self._structured_result(state["plan"])
        cached_state = self._run_cached_insight(state)
        return {
            "tool_outputs": [structured_output, *cached_state["tool_outputs"]],
            "citations": [*structured_citations, *cached_state["citations"]],
            "content_results": (),
        }

    def _structured_result(self, plan: ChatPlan) -> tuple[ToolOutput, list[ChatCitation]]:
        if plan.structured_query is None:  # pragma: no cover - guarded by ChatPlan
            raise RuntimeError("quantitative plan is missing its structured query")
        result = self._structured_query.run(plan.structured_query)
        output = result.model_dump(mode="json", exclude_none=True)
        return output, _structured_citations(result.template, output)

    async def _semantic_result(
        self,
        request: ChatRequest,
        plan: ChatPlan,
    ) -> tuple[tuple[SemanticSearchResult, ...], ToolOutput, list[ChatCitation]]:
        await self._index_service.reconcile()
        if plan.retrieval is None:  # pragma: no cover - guarded by ChatPlan
            raise RuntimeError("content plan is missing retrieval")
        results = await self._semantic_search.run_plan(
            plan.retrieval,
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
                snippet=_relevant_excerpt(item.content, request.message),
            )
            for item in results
        ]
        return results, output, citations


def route_question(question: str) -> ChatRoute:
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
        or _asks_for_application_list(normalized)
        or any(term in normalized for _, terms in _BREAKDOWN_DIMENSION_TERMS for term in terms)
        or len(_matched_sources(normalized)) > 1
    )
    cached_insight = _cached_insight_type(question) is not None
    if cached_insight and any(term in normalized for term in _EXPLICIT_QUANTITATIVE_TERMS):
        return "mixed"
    if cached_insight:
        return "content"
    content = any(term in normalized for term in _CONTENT_TERMS)
    if quantitative and content:
        return "mixed"
    if quantitative:
        return "quantitative"
    return "content"


def _requires_web_search(question: str) -> bool:
    normalized = question.casefold()
    return any(
        term in normalized
        for term in (
            "evidence-based",
            "cite sources",
            "cite useful sources",
            "with sources",
            "current statistics",
            "industry benchmark",
            "people typically",
            "people usually",
            "latest research",
        )
    )


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
    current_normalized = _current_user_question(question).casefold()
    filters = _structured_filters(current_normalized, anchor_at=anchor_at)
    date_window = _date_window_spec(current_normalized)
    list_limit = _requested_list_limit(current_normalized)
    if any(term in normalized for term in ("which month", "busiest month", "most applications")):
        return StructuredQueryRequest(
            template="busiest_application_month", filters=filters, date_window=date_window
        )
    if any(term in normalized for term in ("which companies", "what companies", "list companies")):
        return StructuredQueryRequest(
            template="company_list",
            filters=filters,
            date_window=date_window,
            limit=list_limit,
        )
    if _asks_for_application_list(normalized):
        return StructuredQueryRequest(
            template="application_list",
            filters=filters,
            date_window=date_window,
            limit=(1 if _asks_for_latest_application(current_normalized) else list_limit),
        )
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
    if len(_matched_sources(current_normalized)) > 1:
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
    return StructuredQueryRequest(
        template="summary_counts", filters=filters, date_window=date_window
    )


def _asks_for_latest_application(normalized_question: str) -> bool:
    return bool(
        re.search(
            r"\b(?:latest|last|most recent)\s+application\b",
            normalized_question,
        )
    )


def _asks_for_application_list(normalized_question: str) -> bool:
    return any(
        term in normalized_question
        for term in ("show those applications", "show the applications", "list applications")
    ) or bool(
        re.search(
            r"\b(?:latest|last|most recent)\s+(?:\d{1,3}\s+)?applications?\b",
            normalized_question,
        )
    )


def _requested_list_limit(normalized_question: str) -> int:
    match = re.search(
        r"\b(?:show|list|give me|return)?\s*(?:the\s+)?(?:latest|last|top)?\s*(\d{1,3})\b",
        normalized_question,
    )
    if match is None:
        return 20
    return min(max(int(match.group(1)), 1), 100)


def _date_window_spec(normalized_question: str) -> DateWindowSpec | None:
    for phrase, kind in (
        ("last week", "last_week"),
        ("this week", "this_week"),
        ("last month", "last_month"),
        ("this month", "this_month"),
        ("last year", "last_year"),
        ("this year", "this_year"),
    ):
        if phrase in normalized_question:
            return DateWindowSpec.model_validate({"kind": kind})
    rolling = re.search(r"\b(?:past|last)\s+(\d{1,4})\s+days?\b", normalized_question)
    if rolling is not None:
        return DateWindowSpec(kind="rolling_days", days=int(rolling.group(1)))
    year = re.search(r"\b(?:in|during)\s+((?:19|20)\d{2})\b", normalized_question)
    if year is not None:
        return DateWindowSpec(kind="calendar_year", year=int(year.group(1)))
    return None


def _current_user_question(question: str) -> str:
    marker = "Current user question:"
    if marker not in question:
        return question
    return question.rsplit(marker, maxsplit=1)[1].strip()


def _structured_filters(
    normalized_question: str,
    *,
    anchor_at: datetime | None,
) -> MetricsFilter | None:
    filters = None
    if _date_window_spec(normalized_question) is None or anchor_at is not None:
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
    structured = next((item for item in tool_outputs if item["tool"] == "structured_query"), None)
    if structured is not None:
        rows = structured.get("rows")
        if structured.get("template") == "summary_counts" and isinstance(rows, list):
            parts.append(_synthesize_summary_counts(rows))
        elif structured.get("template") == "rates" and isinstance(rows, list):
            parts.append(_synthesize_rates(rows))
        elif structured.get("template") == "successful_application_segments" and isinstance(
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
        elif structured.get("template") == "application_list" and isinstance(rows, list):
            parts.append(_synthesize_application_list(rows, structured))
        elif structured.get("template") == "company_list" and isinstance(rows, list):
            parts.append(_synthesize_company_list(rows, structured))
        elif structured.get("template") == "busiest_application_month" and isinstance(rows, list):
            parts.append(_synthesize_busiest_month(rows))
        elif structured.get("template") == "total_applications" and isinstance(rows, list):
            parts.append(_synthesize_total_applications(rows))
        elif structured.get("template") == "funnel" and isinstance(rows, list):
            parts.append(_synthesize_funnel(rows))
        elif structured.get("template") == "timing" and isinstance(rows, list):
            parts.append(_synthesize_timing(rows))
        elif structured.get("template") == "personal_ghost_threshold" and isinstance(rows, list):
            parts.append(_synthesize_ghost_threshold(rows))
        elif structured.get("template") == "application_timeseries" and isinstance(rows, list):
            parts.append(_synthesize_application_timeseries(rows))
        elif structured.get("template") == "response_rate_timeseries" and isinstance(rows, list):
            parts.append(_synthesize_response_rate_timeseries(rows))
        elif structured.get("template") == "breakdown" and isinstance(rows, list):
            parts.append(_synthesize_breakdown(rows))
        elif isinstance(rows, list) and rows:
            if structured.get("template") == "live_applications":
                parts.append(_synthesize_live_applications(rows))
            else:
                parts.append(_synthesize_generic_rows(rows))
        else:
            parts.append("The deterministic query found no matching applications.")
    if cached_insight is not None:
        status = cached_insight.get("status")
        content = cached_insight.get("content")
        if status == "available" and isinstance(content, str):
            parts.append(content)
        else:
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
                parts.append(
                    f"The cached {insight_label} insight is stale because its source data changed. "
                    "Regenerate it on the Insights page before relying on it here."
                )
            else:
                parts.append(
                    f"The {insight_label} insight has not been generated yet. Generate it on the "
                    "Insights page, then ask again."
                )
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
            excerpt = citation.snippet or " ".join(result.content.split())[:280]
            excerpts.append(f'"{excerpt}" [{citation.citation_id}]')
        parts.append("Relevant source email evidence: " + " ".join(excerpts))
    elif route in {"content", "mixed"} and cached_insight is None:
        parts.append(
            "I cannot answer the email-content portion because no retained job-related "
            "source email was retrieved."
        )
    return " ".join(parts)


def _relevant_excerpt(content: str, question: str, *, max_chars: int = 280) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_chars:
        return normalized

    query_terms = {
        token
        for token in re.findall(r"[a-z0-9]+", question.casefold())
        if len(token) >= 3 and token not in _EXCERPT_STOP_WORDS
    }
    matches = [
        match for match in re.finditer(r"[^.!?]+[.!?]?", normalized) if match.group().strip()
    ]
    ranked = sorted(
        matches,
        key=lambda match: (
            sum(
                len(term)
                for term in query_terms
                if re.search(rf"\b{re.escape(term)}\b", match.group().casefold())
            ),
            -match.start(),
        ),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    if best is None or not any(
        re.search(rf"\b{re.escape(term)}\b", best.group().casefold()) for term in query_terms
    ):
        return normalized[:max_chars]

    sentence = best.group().strip()
    if len(sentence) <= max_chars:
        return sentence

    matching_positions = [
        match.start()
        for term in query_terms
        if (match := re.search(rf"\b{re.escape(term)}\b", sentence.casefold())) is not None
    ]
    focus = min(matching_positions, default=0)
    start = max(0, min(focus - max_chars // 2, len(sentence) - max_chars))
    excerpt = sentence[start : start + max_chars].strip()
    prefix = "... " if start else ""
    suffix = " ..." if start + max_chars < len(sentence) else ""
    return f"{prefix}{excerpt}{suffix}"


def _synthesize_live_applications(rows: list[object]) -> str:
    waiting: list[tuple[int, str]] = []
    overdue: list[tuple[int, str]] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        if values.get("waiting_on_employer") is False:
            continue
        company = values.get("company")
        role = values.get("role_title")
        application_id = values.get("application_id")
        if not all(isinstance(value, str) for value in (company, role, application_id)):
            continue
        citation_id = f"application:{application_id}"
        label = f"{company} - {role} [{citation_id}]"
        days_waiting = values.get("days_waiting")
        days = days_waiting if isinstance(days_waiting, int) else 0
        waiting.append((days, label))
        if values.get("follow_up_due") is True:
            overdue.append((days, f"{label} ({days} days waiting)"))

    if not waiting:
        return "The deterministic query found no applications awaiting an employer response."
    waiting.sort(reverse=True)
    overdue.sort(reverse=True)
    visible_waiting = [label for _, label in waiting[:25]]
    visible_overdue = [label for _, label in overdue[:25]]
    waiting_suffix = f"; plus {len(waiting) - 25} more" if len(waiting) > 25 else ""
    overdue_suffix = f"; plus {len(overdue) - 25} more" if len(overdue) > 25 else ""
    overdue_text = ", ".join(visible_overdue) if visible_overdue else "None"
    return (
        f"Waiting on: {', '.join(visible_waiting)}{waiting_suffix}. "
        f"Overdue for follow-up: {overdue_text}{overdue_suffix}."
    )


def _synthesize_application_list(rows: list[object], output: ToolOutput) -> str:
    total = output.get("total_matching_count", len(rows))
    if not rows:
        return "I found no submitted applications matching that request."
    returned = output.get("returned_count", len(rows))
    if returned == 1:
        return "Here is the matching application with its company, role, and status."
    suffix = f" Showing the first {returned}." if returned != total else ""
    return f"I found {total} matching submitted applications.{suffix}"


def _synthesize_total_applications(rows: list[object]) -> str:
    values = rows[0].get("values") if rows and isinstance(rows[0], dict) else None
    count = values.get("application_count") if isinstance(values, dict) else None
    if not isinstance(count, int):
        return "I found no matching submitted applications."
    label = "application" if count == 1 else "applications"
    return f"You submitted {count} matching {label}."


def _synthesize_funnel(rows: list[object]) -> str:
    stages = [
        f"{str(row.get('label')).replace('_', ' ')}: {row['values']['count']}"
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("values"), dict)
        and isinstance(row["values"].get("count"), int)
    ]
    return "Your application funnel is " + "; ".join(stages) + "."


def _synthesize_timing(rows: list[object]) -> str:
    summaries: list[str] = []
    labels = {
        "time_to_first_response": "first response",
        "time_to_rejection": "rejection",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = row.get("values")
        if not isinstance(values, dict):
            continue
        hours = values.get("average_hours")
        sample_size = values.get("application_count")
        if not isinstance(hours, int | float) or not isinstance(sample_size, int):
            continue
        label = labels.get(str(row.get("label")), str(row.get("label")).replace("_", " "))
        summaries.append(f"{label}: {hours / 24:.1f} days across {sample_size} applications")
    return "Average timing for the matching applications is " + "; ".join(summaries) + "."


def _synthesize_ghost_threshold(rows: list[object]) -> str:
    values = rows[0].get("values") if rows and isinstance(rows[0], dict) else None
    if not isinstance(values, dict) or not isinstance(values.get("threshold_days"), int):
        return "There is not enough history to estimate a ghost threshold."
    days = values["threshold_days"]
    sample_size = values.get("response_sample_size")
    sample = f" based on {sample_size} responses" if isinstance(sample_size, int) else ""
    return f"Your effective ghost threshold is {days} days{sample}."


def _synthesize_application_timeseries(rows: list[object]) -> str:
    points = [
        f"{row['values']['period_start']}: {row['values']['application_count']}"
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("values"), dict)
        and isinstance(row["values"].get("period_start"), str)
        and isinstance(row["values"].get("application_count"), int)
    ]
    return "Application volume by period is " + "; ".join(points) + "."


def _synthesize_response_rate_timeseries(rows: list[object]) -> str:
    points = [
        f"{row['values']['period_start']}: {row['values']['response_rate']:.1%} "
        f"({row['values']['response_count']} of {row['values']['application_count']})"
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("values"), dict)
        and isinstance(row["values"].get("period_start"), str)
        and isinstance(row["values"].get("response_rate"), int | float)
        and isinstance(row["values"].get("response_count"), int)
        and isinstance(row["values"].get("application_count"), int)
    ]
    return "Response rate by period is " + "; ".join(points) + "."


def _synthesize_breakdown(rows: list[object]) -> str:
    segments = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = row.get("values")
        if not isinstance(values, dict):
            continue
        count = values.get("application_count")
        response_rate = values.get("response_rate")
        interview_rate = values.get("interview_rate")
        if not isinstance(count, int):
            continue
        detail = f"{row.get('label')}: {count} applications"
        if isinstance(response_rate, int | float):
            detail += f", {response_rate:.1%} response rate"
        if isinstance(interview_rate, int | float):
            detail += f", {interview_rate:.1%} interview rate"
        segments.append(detail)
    return "The matching breakdown is " + "; ".join(segments) + "."


def _synthesize_generic_rows(rows: list[object]) -> str:
    summaries: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = row.get("values")
        if not isinstance(values, dict):
            continue
        details = ", ".join(
            f"{str(key).replace('_', ' ')} {value}"
            for key, value in values.items()
            if value is not None
        )
        summaries.append(f"{row.get('label')}: {details}")
    return "The deterministic data shows " + "; ".join(summaries) + "."


def _synthesize_summary_counts(rows: list[object]) -> str:
    values = rows[0].get("values") if rows and isinstance(rows[0], dict) else None
    if not isinstance(values, dict):
        return "I found no matching submitted applications."
    total = int(values.get("total_applications", 0))
    companies = int(values.get("distinct_company_count", 0))
    responses = int(values.get("human_response_count", 0))
    interviews = int(values.get("interview_invitation_count", 0))
    offers = int(values.get("offers_received", 0))
    application_label = "application" if total == 1 else "applications"
    company_label = "company" if companies == 1 else "companies"
    return (
        f"You submitted {total} {application_label} across {companies} {company_label} in that "
        "scope. "
        f"{responses} received a response, {interviews} reached an interview, and {offers} "
        "received an offer."
    )


def _synthesize_rates(rows: list[object]) -> str:
    summaries: list[str] = []
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            continue
        label = str(row.get("label", "rate")).replace("_", " ") if isinstance(row, dict) else "rate"
        rate = values.get("rate")
        if isinstance(rate, int | float):
            summaries.append(f"{label}: {rate:.1%}")
    return "Your matching rates are " + "; ".join(summaries) + "."


def _synthesize_company_list(rows: list[object], output: ToolOutput) -> str:
    total = output.get("total_matching_count", len(rows))
    if not rows:
        return "I found no companies matching that request."
    companies = [
        str(row.get("values", {}).get("company"))
        for row in rows[:20]
        if isinstance(row, dict) and isinstance(row.get("values"), dict)
    ]
    suffix = "" if len(rows) <= 20 else f", plus {len(rows) - 20} more"
    return f"You applied to {total} matching companies: {', '.join(companies)}{suffix}."


def _synthesize_busiest_month(rows: list[object]) -> str:
    if not rows:
        return "There is not enough application history to identify a busiest month."
    summaries = [
        f"{row['values']['month_start']}: {row['values']['application_count']} applications"
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("values"), dict)
    ]
    return "Your busiest application month was " + "; tied with ".join(summaries) + "."


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
    if template in {"live_applications", "application_list"}:
        rows = output.get("rows")
        if isinstance(rows, list):
            result = []
            for row in rows:
                values = row.get("values") if isinstance(row, dict) else None
                if not isinstance(values, dict):
                    continue
                application_id = values.get("application_id")
                if isinstance(application_id, str):
                    result.append(
                        ChatCitation(
                            citation_id=f"application:{application_id}",
                            source="application",
                            application_id=application_id,
                            company=(str(values.get("company")) if values.get("company") else None),
                            role_title=(
                                str(values.get("role_title")) if values.get("role_title") else None
                            ),
                            current_status=(
                                str(values.get("current_status") or values.get("status"))
                                if values.get("current_status") or values.get("status")
                                else None
                            ),
                            first_seen_at=values.get("first_seen_at"),
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
