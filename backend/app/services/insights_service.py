from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from app.config import AppSettings, LLMProviderName
from app.db.repositories import InsightRepository
from app.models import InsightInput, InsightInputEvidence, InsightInputFact, InsightRecord
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

INSIGHT_GENERATION_PROMPT_VERSION = "v1"
INSIGHT_GENERATION_MAX_OUTPUT_TOKENS = 1200
INSIGHT_GENERATION_TEMPERATURE = 0.2
_CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_CITATION_LIKE_TOKEN_PATTERN = re.compile(r"^(?:\d+|[A-Za-z]+-\d+|\S*[:|]\S*)$")
_SENTENCE_PATTERN = re.compile(r"[^.!?\n]+(?:[.!?]|\n|$)")
_UNGROUNDED_INSIGHT_MESSAGE = "LLM returned ungrounded insight content."


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
        """Return a cached insight or synthesize and persist a fresh one."""

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
        evidence = scoped_evidence[:max_evidence_items]
        insight_input = InsightInput(
            type=insight_type,
            facts=self._build_facts(insight_type, evidence=evidence),
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
        *,
        evidence: list[InsightInputEvidence],
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
    if insight_type == "skill_gaps":
        return (
            "For skill_gaps, answer Q-42: identify technologies and skills that recur "
            "in rejected roles. Use rejected_skill_counts, rejected application tech_stack "
            "values, and cited rejection or feedback evidence. Do not treat skills from "
            "interviews or offers as gaps unless they also appear in rejected-role evidence."
        )
    return ""


def _validated_insight_content(
    response: LLMGenerationResponse,
    insight_input: InsightInput,
) -> str:
    content = response.content.strip()
    if response.finish_reason is not LLMFinishReason.STOP or not content:
        raise LLMProviderResponseError(public_message="LLM returned invalid insight content.")
    _validate_grounding_citations(content, insight_input)
    return content


def _validate_grounding_citations(content: str, insight_input: InsightInput) -> None:
    allowed_citation_ids = {evidence.citation_id for evidence in insight_input.evidence}
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

    if (
        not cited_evidence_ids
        or invalid_citation_ids
        or _has_ungrounded_claim(content, valid_citation_spans)
    ):
        raise LLMProviderResponseError(public_message=_UNGROUNDED_INSIGHT_MESSAGE)


def _split_citation_tokens(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


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
    return bool(re.sub(r"[\s.!?]+", "", "".join(parts)))


def _has_citation_between(
    citation_spans: list[tuple[int, int]],
    start: int,
    end: int,
) -> bool:
    return any(span_start >= start and span_end <= end for span_start, span_end in citation_spans)


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
    payload = insight_input.model_dump(mode="json", exclude={"inputs_hash"})
    return _hash_payload(payload)


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class _EvidenceScope:
    application_statuses: tuple[ApplicationStatus, ...] = ()
    event_types: tuple[ApplicationEventType, ...] = ()
    newest_first: bool = False


def _evidence_scope(insight_type: InsightType) -> _EvidenceScope:
    if insight_type == "why_rejected":
        return _EvidenceScope(event_types=("rejection",))
    if insight_type == "skill_gaps":
        return _EvidenceScope(application_statuses=("rejected",))
    if insight_type == "role_fit":
        return _EvidenceScope(application_statuses=("interview", "offer", "rejected", "ghosted"))
    if insight_type == "weekly_actions":
        return _EvidenceScope(
            application_statuses=("applied", "in_review", "assessment", "interview"),
            newest_first=True,
        )
    return _EvidenceScope()
