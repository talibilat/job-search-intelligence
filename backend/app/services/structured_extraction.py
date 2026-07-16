from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.config import AppSettings, ClassificationMode, LLMProviderName
from app.db.repositories import ClassificationRunRepository, EmailRepository
from app.models import ClassificationRunRecord, EmailClassificationCandidate
from app.pipeline.classify import (
    AcceptedLLMExtraction,
    ClassificationPromptEmail,
    MalformedLLMExtraction,
    MalformedLLMExtractionReason,
    build_classification_prompt_request,
    parse_llm_extraction_response,
)
from app.providers.llm import LLMProvider, LLMTokenUsage
from app.providers.llm.errors import LLMProviderError

type Clock = Callable[[], datetime]
type RunIdFactory = Callable[[], str]


class StructuredExtractionRunResult(BaseModel):
    """Typed result for one structured extraction batch."""

    model_config = ConfigDict(frozen=True)

    run_record: ClassificationRunRecord
    accepted_results: tuple[AcceptedLLMExtraction, ...] = Field(default_factory=tuple)
    malformed_results: tuple[MalformedLLMExtraction, ...] = Field(default_factory=tuple)


class StructuredExtractionService:
    """Run retained email candidates through classification and extraction."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        email_repository: EmailRepository,
        classification_run_repository: ClassificationRunRepository,
        llm_provider: LLMProvider,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory | None = None,
    ) -> None:
        self._settings = settings
        self._email_repository = email_repository
        self._classification_run_repository = classification_run_repository
        self._llm_provider = llm_provider
        self._clock = clock or _utcnow
        self._run_id_factory = run_id_factory or _new_run_id

    async def run_batch(
        self,
        *,
        limit: int | None = None,
        excluded_email_ids: tuple[str, ...] = (),
    ) -> StructuredExtractionRunResult:
        """Classify and extract one configured batch of retained email candidates."""

        model = _classification_model(self._settings)
        prompt_version = self._settings.classification_prompt_version
        started_at = self._clock()
        candidates = self._email_repository.list_classification_candidates(
            provider=self._settings.email_provider,
            model=model,
            prompt_version=prompt_version,
            limit=min(
                limit or self._settings.classification_batch_size,
                self._settings.classification_batch_size,
            ),
            excluded_email_ids=excluded_email_ids,
        )
        semaphore = asyncio.Semaphore(self._settings.classification_concurrency)

        async def classify(
            candidate: EmailClassificationCandidate,
        ) -> tuple[AcceptedLLMExtraction | MalformedLLMExtraction, LLMTokenUsage | None]:
            request = build_classification_prompt_request(
                ClassificationPromptEmail(
                    email_id=candidate.email_id,
                    from_addr=candidate.from_addr,
                    subject=candidate.subject,
                    sent_at=candidate.sent_at,
                    body_text=candidate.body_text,
                ),
                prompt_version=prompt_version,
                model=model,
            )
            async with semaphore:
                try:
                    response = await self._llm_provider.generate(request)
                except LLMProviderError:
                    return MalformedLLMExtraction(
                        email_id=candidate.email_id,
                        model=model,
                        prompt_version=prompt_version,
                        reason=MalformedLLMExtractionReason.PROVIDER_ERROR,
                        message="LLM provider could not classify this email.",
                    ), None
            return parse_llm_extraction_response(
                email_id=candidate.email_id,
                response=response.model_copy(update={"model": model}),
                prompt_version=prompt_version,
                classified_at=self._clock(),
            ), response.usage

        outcomes = await asyncio.gather(*(classify(candidate) for candidate in candidates))
        accepted_results: list[AcceptedLLMExtraction] = []
        malformed_results: list[MalformedLLMExtraction] = []
        token_usage = _TokenUsageAccumulator()
        for extraction_result, usage in outcomes:
            token_usage.add(usage)
            if isinstance(extraction_result, AcceptedLLMExtraction):
                accepted_results.append(extraction_result)
            else:
                malformed_results.append(extraction_result)

        completed_at = self._clock()
        run_record = ClassificationRunRecord(
            id=self._run_id_factory(),
            provider=self._llm_provider.provider_name,
            model=model,
            prompt_version=prompt_version,
            started_at=started_at,
            completed_at=completed_at,
            candidate_count=len(candidates),
            classified_count=len(accepted_results),
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            total_tokens=token_usage.total_tokens,
            estimated_cost_usd=_estimated_cost_usd(
                settings=self._settings,
                prompt_tokens=token_usage.prompt_tokens,
                completion_tokens=token_usage.completion_tokens,
            ),
        )
        should_commit = not self._email_repository.connection.in_transaction
        with self._email_repository.transaction():
            self._email_repository.upsert_email_classifications(
                result.classification for result in accepted_results
            )
            self._classification_run_repository.upsert_run(run_record)
        if should_commit:
            self._email_repository.connection.commit()
        return StructuredExtractionRunResult(
            run_record=run_record,
            accepted_results=tuple(accepted_results),
            malformed_results=tuple(malformed_results),
        )


class _TokenUsageAccumulator:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def add(self, usage: LLMTokenUsage | None) -> None:
        if usage is None:
            return

        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += max(
            usage.total_tokens,
            usage.prompt_tokens + usage.completion_tokens,
        )


def _classification_model(settings: AppSettings) -> str:
    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return settings.azure_openai_chat_deployment or "unconfigured"
    return settings.ollama_chat_model


def _estimated_cost_usd(
    *,
    settings: AppSettings,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    if settings.classification_mode is ClassificationMode.LOCAL:
        return Decimal("0")

    input_rate = Decimal(str(settings.classification_input_cost_per_1k_units_usd))
    output_rate = Decimal(str(settings.classification_output_cost_per_1k_units_usd))
    if input_rate == 0 or output_rate == 0:
        return Decimal("0")

    return (
        (Decimal(prompt_tokens) / Decimal(1000) * input_rate)
        + (Decimal(completion_tokens) / Decimal(1000) * output_rate)
    ).quantize(Decimal("0.000001"))


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return uuid4().hex
