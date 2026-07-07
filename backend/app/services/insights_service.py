from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from app.config import AppSettings, LLMProviderName
from app.db.repositories import InsightRepository
from app.models import (
    InsightInput,
    InsightInputEvidence,
    InsightInputFact,
    InsightRecord,
    InsightRoleOutcomeSummary,
)
from app.models.records import ApplicationEventType, ApplicationStatus, InsightType
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMProvider,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
)

type Clock = Callable[[], datetime]

INSIGHT_GENERATION_PROMPT_VERSION = "v2"
INSIGHT_GENERATION_MAX_OUTPUT_TOKENS = 1200
INSIGHT_GENERATION_TEMPERATURE = 0.2
WEEKLY_ACTIONS_VALIDATION_ERROR = "Weekly actions insight must contain exactly three cited actions."
_CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_CITATION_LIKE_TOKEN_PATTERN = re.compile(r"^(?:\d+|[A-Za-z]+-\d+|\S*[:|]\S*)$")
_ROLE_FIT_WIN_STATUSES: tuple[ApplicationStatus, ...] = ("interview", "offer")
_ROLE_FIT_LOSS_STATUSES: tuple[ApplicationStatus, ...] = ("rejected", "ghosted")
_SENTENCE_PATTERN = re.compile(r"[^.!?\n]+(?:[.!?]|\n|$)")
_INSUFFICIENT_EVIDENCE_TERMS = (
    "insufficient",
    "not enough",
    "missing evidence",
    "no evidence",
    "cannot determine",
    "can't determine",
    "unable to determine",
)
_UNGROUNDED_INSIGHT_MESSAGE = "LLM returned ungrounded insight content."
STORY_EVIDENCE_WINDOW_DAYS = 366


class InsightGenerationResult(BaseModel):
    """Provider-backed narrative insight generation result."""

    model_config = ConfigDict(frozen=True)

    insight: InsightRecord
    input: InsightInput
    cached: bool


class InsightGenerationService:
    """Generate cached narrative insights through the configured LLM provider."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        insight_repository: InsightRepository,
        llm_provider: LLMProvider,
        input_builder: InsightInputBuilder | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._settings = settings
        self._insight_repository = insight_repository
        self._llm_provider = llm_provider
        self._input_builder = input_builder or InsightInputBuilder(insight_repository)
        self._clock = clock or _utcnow

    async def generate_insight(
        self,
        insight_type: InsightType,
        *,
        max_evidence_items: int = 100,
        force: bool = False,
    ) -> InsightGenerationResult:
        """Return a cached insight or synthesize, validate, and persist a fresh one."""

        insight_input = self._input_builder.build(
            insight_type,
            max_evidence_items=max_evidence_items,
        )
        model = _configured_chat_model(self._settings)

        if not force:
            cached = self._insight_repository.get_cached_insight(
                insight_type=insight_type,
                inputs_hash=insight_input.inputs_hash,
                model=model,
            )
            if cached is not None:
                return InsightGenerationResult(
                    insight=cached,
                    input=insight_input,
                    cached=True,
                )

        response = await self._llm_provider.generate(
            build_insight_generation_request(insight_input, model=model),
        )
        content = _validated_insight_content(response, insight_input)
        insight = self._insight_repository.save_generated_insight(
            insight_type=insight_type,
            content=content,
            inputs_hash=insight_input.inputs_hash,
            model=model,
            generated_at=self._clock(),
        )
        return InsightGenerationResult(
            insight=insight,
            input=insight_input,
            cached=False,
        )


def build_insight_generation_request(
    insight_input: InsightInput,
    *,
    model: str,
) -> LLMGenerationRequest:
    """Build a provider-neutral narrative insight generation request."""

    return LLMGenerationRequest(
        messages=(
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content=_insight_system_prompt(insight_input.type),
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content=json.dumps(
                    insight_input.model_dump(mode="json"),
                    sort_keys=False,
                ),
            ),
        ),
        model=model,
        response_format=LLMResponseFormat.TEXT,
        options=LLMGenerationOptions(
            temperature=INSIGHT_GENERATION_TEMPERATURE,
            max_output_tokens=INSIGHT_GENERATION_MAX_OUTPUT_TOKENS,
        ),
    )


class InsightInputBuilder:
    """Build deterministic, cited input packages for narrative insight synthesis."""

    def __init__(self, insight_repository: InsightRepository) -> None:
        self._insight_repository = insight_repository

    def build(
        self,
        insight_type: InsightType,
        *,
        max_evidence_items: int = 100,
    ) -> InsightInput:
        if max_evidence_items < 1:
            msg = "max_evidence_items must be at least 1"
            raise ValueError(msg)

        scope = _evidence_scope(insight_type)
        scoped_evidence = self._insight_repository.list_input_evidence(
            application_statuses=scope.application_statuses,
            event_types=scope.event_types,
            newest_first=scope.newest_first,
        )
        if insight_type == "story":
            scoped_evidence = _recent_story_evidence(scoped_evidence)
            evidence = scoped_evidence[-max_evidence_items:]
        else:
            evidence = (
                scoped_evidence
                if scope.include_all_evidence
                else scoped_evidence[:max_evidence_items]
            )
        insight_input = InsightInput(
            type=insight_type,
            facts=self._build_facts(insight_type, scoped_evidence),
            evidence=evidence,
            source_fingerprint=_hash_payload(
                [item.model_dump(mode="json") for item in scoped_evidence],
            ),
            inputs_hash="",
        )
        return insight_input.model_copy(
            update={"inputs_hash": _hash_insight_input(insight_input)},
        )

    def _build_facts(
        self,
        insight_type: InsightType,
        scoped_evidence: list[InsightInputEvidence],
    ) -> list[InsightInputFact]:
        facts = [
            InsightInputFact(
                name="total_applications",
                value=self._insight_repository.count_applications(),
                source="applications",
            ),
            InsightInputFact(
                name="status_counts",
                value=self._insight_repository.count_applications_by_status(),
                source="applications",
            ),
            InsightInputFact(
                name="source_counts",
                value=self._insight_repository.count_applications_by_source(),
                source="applications",
            ),
            InsightInputFact(
                name="sponsorship_counts",
                value=self._insight_repository.count_applications_by_sponsorship(),
                source="applications",
            ),
            InsightInputFact(
                name="work_mode_counts",
                value=self._insight_repository.count_applications_by_work_mode(),
                source="applications",
            ),
            InsightInputFact(
                name="event_type_counts",
                value=self._insight_repository.count_events_by_type(),
                source="application_events",
            ),
        ]
        if insight_type == "skill_gaps":
            facts.append(
                InsightInputFact(
                    name="rejected_skill_counts",
                    value=self._insight_repository.count_rejected_application_skills(),
                    source="applications",
                ),
            )
        if insight_type == "role_fit":
            facts.append(
                InsightInputFact(
                    name="role_outcome_summaries",
                    value=_build_role_outcome_summaries(scoped_evidence),
                    source="applications",
                ),
            )
        return facts


def _insight_system_prompt(insight_type: InsightType) -> str:
    lines = [
        "You generate cached narrative insights for JobTracker.",
        f"Prompt version: {INSIGHT_GENERATION_PROMPT_VERSION}",
        "Use only the deterministic facts and cited evidence in the user payload.",
        "Never produce authoritative counts, rates, or group-by numbers beyond the "
        "provided deterministic facts.",
        "Never emit raw SQL.",
        "Every claim about a pattern, reason, skill, role, or action must cite one "
        "or more source evidence citation_id values.",
        "Use only the provided citation_id values and format citations in square brackets.",
        "If the evidence is insufficient, say what is missing instead of guessing.",
        "Return plain text only. Do not wrap the answer in JSON or Markdown tables.",
    ]
    type_prompt = _insight_type_prompt(insight_type)
    if type_prompt:
        lines.extend(("", type_prompt))
    return "\n".join(lines)


def _insight_type_prompt(insight_type: InsightType) -> str:
    if insight_type == "why_rejected":
        return (
            "For Q-40 / why_rejected, answer why rejections happen by identifying "
            "recurring rejection themes across rejection emails. Group the answer by "
            "theme, explain why each theme appears, and cite rejection-email evidence "
            "for every theme. Do not infer causes that are absent from the cited "
            "rejection evidence."
        )
    if insight_type == "role_fit":
        return (
            "For role_fit, answer Q-44: which roles genuinely suit the user best based "
            "on patterns of wins. Treat interviews and offers as wins, compare them "
            "against rejected and ghosted outcomes, and use role_outcome_summaries as "
            "deterministic role-level evidence derived from the cited applications. "
            "each role_outcome_summary includes citation_ids; cite the applications or "
            "emails behind each role-fit claim and call out thin evidence instead of "
            "overstating fit."
        )
    if insight_type == "skill_gaps":
        return (
            "For skill_gaps, answer Q-42: identify technologies and skills that recur "
            "in rejected roles. Use rejected_skill_counts, rejected application tech_stack "
            "values, and cited rejection or feedback evidence. Do not treat skills from "
            "interviews or offers as gaps unless they also appear in rejected-role evidence."
        )
    if insight_type == "weekly_actions":
        return (
            "For weekly_actions insights, answer Q-45: What are the 3 concrete things I "
            "should do next week to improve outcomes? Return exactly three numbered "
            "actions, one per line, numbered 1. through 3. Each action must be concrete, "
            "specific to the provided evidence, and executable during the next week. "
            "Each action line must cite at least one provided citation_id in square "
            "brackets. Do not include an introduction, recap, or extra action beyond "
            "the three lines."
        )
    if insight_type == "story":
        return "\n".join(
            (
                "Answer Q-46: What's the story my last 6 to 12 months of job searching tells?",
                "Write a chronological narrative of the recent search arc, including phases, "
                "turning points, repeated patterns, and what changed over time.",
                "Ground the story in the provided recent evidence window and cite each narrative "
                "beat with one or more citation_id values.",
            ),
        )
    return ""


def _recent_story_evidence(
    evidence: list[InsightInputEvidence],
) -> list[InsightInputEvidence]:
    timestamps = [_as_utc(timestamp) for item in evidence if (timestamp := _story_timestamp(item))]
    if not timestamps:
        return []
    cutoff = max(timestamps) - timedelta(days=STORY_EVIDENCE_WINDOW_DAYS)
    return [
        item
        for item in evidence
        if (timestamp := _story_timestamp(item)) is not None and _as_utc(timestamp) >= cutoff
    ]


def _story_timestamp(evidence: InsightInputEvidence) -> datetime | None:
    return evidence.event_at or evidence.email_sent_at


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validated_insight_content(
    response: LLMGenerationResponse,
    insight_input: InsightInput,
) -> str:
    content = response.content.strip()
    if response.finish_reason is not LLMFinishReason.STOP or not content:
        raise LLMProviderResponseError(public_message="LLM returned invalid insight content.")
    if insight_input.type == "weekly_actions":
        _validate_weekly_actions_content(
            content,
            {evidence.citation_id for evidence in insight_input.evidence},
        )
    _validate_grounding_citations(content, insight_input)
    return content


def _validate_weekly_actions_content(
    content: str,
    allowed_citation_ids: set[str],
) -> None:
    action_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(action_lines) != 3:
        raise LLMProviderResponseError(public_message=WEEKLY_ACTIONS_VALIDATION_ERROR)

    for expected_number, action_line in enumerate(action_lines, start=1):
        line_prefix = f"{expected_number}. "
        if not action_line.startswith(line_prefix):
            raise LLMProviderResponseError(public_message=WEEKLY_ACTIONS_VALIDATION_ERROR)
        citation_ids = _extract_citation_ids(action_line)
        if not citation_ids or citation_ids - allowed_citation_ids:
            raise LLMProviderResponseError(public_message=WEEKLY_ACTIONS_VALIDATION_ERROR)
        action_text = _CITATION_PATTERN.sub("", action_line.removeprefix(line_prefix)).strip()
        if not re.search(r"[A-Za-z0-9]", action_text):
            raise LLMProviderResponseError(public_message=WEEKLY_ACTIONS_VALIDATION_ERROR)


def _extract_citation_ids(value: str) -> set[str]:
    citation_ids: set[str] = set()
    for bracket_content in _CITATION_PATTERN.findall(value):
        citation_ids.update(
            _split_citation_tokens(bracket_content),
        )
    return citation_ids


def _validate_grounding_citations(content: str, insight_input: InsightInput) -> None:
    allowed_citation_ids = _allowed_citation_ids(insight_input)
    cited_evidence_ids: set[str] = set()
    invalid_citation_ids: set[str] = set()
    valid_citation_spans: list[tuple[int, int]] = []

    for match in _CITATION_PATTERN.finditer(content):
        for citation_id in _split_citation_tokens(match.group(1)):
            if not _is_citation_like_token(citation_id, allowed_citation_ids):
                continue
            if citation_id in allowed_citation_ids:
                cited_evidence_ids.add(citation_id)
                valid_citation_spans.append(match.span())
            else:
                invalid_citation_ids.add(citation_id)

    if invalid_citation_ids:
        raise LLMProviderResponseError(public_message=_UNGROUNDED_INSIGHT_MESSAGE)
    if not allowed_citation_ids and not cited_evidence_ids:
        if _states_insufficient_evidence(content):
            return
        raise LLMProviderResponseError(public_message=_UNGROUNDED_INSIGHT_MESSAGE)
    if (
        not cited_evidence_ids
        or _has_ungrounded_claim(content, valid_citation_spans)
    ):
        raise LLMProviderResponseError(public_message=_UNGROUNDED_INSIGHT_MESSAGE)


def _split_citation_tokens(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def _is_citation_like_token(value: str, allowed_citation_ids: set[str]) -> bool:
    return value in allowed_citation_ids or bool(_CITATION_LIKE_TOKEN_PATTERN.fullmatch(value))


def _has_ungrounded_claim(content: str, citation_spans: list[tuple[int, int]]) -> bool:
    pending_claim = False
    pending_claim_end = 0

    for match in _SENTENCE_PATTERN.finditer(content):
        sentence_start, sentence_end = match.span()
        if not _has_claim_text(content, sentence_start, sentence_end, citation_spans):
            if pending_claim and _has_citation_between(
                citation_spans,
                pending_claim_end,
                sentence_end,
            ):
                pending_claim = False
            continue
        if pending_claim:
            return True
        if _has_citation_between(citation_spans, sentence_start, sentence_end):
            pending_claim = False
            continue
        pending_claim = True
        pending_claim_end = sentence_end

    return pending_claim


def _has_claim_text(
    content: str,
    start: int,
    end: int,
    citation_spans: list[tuple[int, int]],
) -> bool:
    parts: list[str] = []
    cursor = start
    for span_start, span_end in citation_spans:
        if span_end <= start or span_start >= end:
            continue
        parts.append(content[cursor : max(cursor, span_start)])
        cursor = max(cursor, span_end)
    parts.append(content[cursor:end])
    claim_text = re.sub(r"^\s*\d+\.\s*", "", "".join(parts))
    return bool(re.sub(r"[\s.!?]+", "", claim_text))


def _has_citation_between(
    citation_spans: list[tuple[int, int]],
    start: int,
    end: int,
) -> bool:
    return any(span_start >= start and span_end <= end for span_start, span_end in citation_spans)


def _states_insufficient_evidence(content: str) -> bool:
    normalized = content.casefold()
    return any(term in normalized for term in _INSUFFICIENT_EVIDENCE_TERMS)


def _allowed_citation_ids(insight_input: InsightInput) -> set[str]:
    citation_ids = {evidence.citation_id for evidence in insight_input.evidence}
    for fact in insight_input.facts:
        if fact.name != "role_outcome_summaries" or not isinstance(fact.value, list):
            continue
        for summary in fact.value:
            if isinstance(summary, InsightRoleOutcomeSummary):
                citation_ids.update(summary.citation_ids)
    return citation_ids


def _configured_chat_model(settings: AppSettings) -> str:
    model = (
        settings.azure_openai_chat_deployment
        if settings.llm_provider is LLMProviderName.AZURE_OPENAI
        else settings.ollama_chat_model
    ).strip()
    if not model:
        raise LLMProviderUnavailableError(
            public_message="Configured LLM provider chat model is missing.",
        )
    return model


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_insight_input(insight_input: InsightInput) -> str:
    payload = {
        "prompt_version": INSIGHT_GENERATION_PROMPT_VERSION,
        "input": insight_input.model_dump(mode="json", exclude={"inputs_hash"}),
    }
    return _hash_payload(payload)


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class _EvidenceScope:
    application_statuses: tuple[ApplicationStatus, ...] = ()
    event_types: tuple[ApplicationEventType, ...] = ()
    newest_first: bool = False
    include_all_evidence: bool = False


def _evidence_scope(insight_type: InsightType) -> _EvidenceScope:
    if insight_type == "why_rejected":
        return _EvidenceScope(event_types=("rejection",))
    if insight_type == "skill_gaps":
        return _EvidenceScope(application_statuses=("rejected",))
    if insight_type == "strongest_weakest_signals":
        return _EvidenceScope(include_all_evidence=True)
    if insight_type == "role_fit":
        return _EvidenceScope()
    if insight_type == "weekly_actions":
        return _EvidenceScope(
            application_statuses=("applied", "in_review", "assessment", "interview"),
            newest_first=True,
        )
    return _EvidenceScope()


def _build_role_outcome_summaries(
    evidence: list[InsightInputEvidence],
) -> list[InsightRoleOutcomeSummary]:
    application_summaries: dict[str, tuple[str, ApplicationStatus]] = {}
    role_citation_ids: dict[str, list[str]] = {}
    for item in evidence:
        role_title = item.role_title.strip()
        if not role_title:
            continue
        role_citation_ids.setdefault(role_title, [])
        if item.citation_id not in role_citation_ids[role_title]:
            role_citation_ids[role_title].append(item.citation_id)
        if item.application_id not in application_summaries:
            application_summaries[item.application_id] = (
                role_title,
                item.application_status,
            )

    role_status_counts: dict[str, dict[str, int]] = {}
    for role_title, status in application_summaries.values():
        role_status_counts.setdefault(role_title, {}).setdefault(status, 0)
        role_status_counts[role_title][status] += 1

    summaries = [
        InsightRoleOutcomeSummary(
            role_title=role_title,
            application_count=sum(status_counts.values()),
            win_count=sum(
                count for status, count in status_counts.items() if status in _ROLE_FIT_WIN_STATUSES
            ),
            loss_count=sum(
                count
                for status, count in status_counts.items()
                if status in _ROLE_FIT_LOSS_STATUSES
            ),
            status_counts=dict(sorted(status_counts.items())),
            citation_ids=role_citation_ids[role_title],
        )
        for role_title, status_counts in role_status_counts.items()
    ]
    return sorted(
        summaries,
        key=lambda summary: (
            -summary.win_count,
            summary.loss_count,
            -summary.application_count,
            summary.role_title.casefold(),
        ),
    )
