from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import AppSettings, LLMProviderName
from app.models import EmailClassificationCandidate, EmailClassificationRecord
from app.pipeline.classify import (
    ClassificationPromptEmail,
    MalformedLLMExtraction,
    build_classification_prompt_request,
    parse_classification_generation_response,
)
from app.providers.llm import LLMGenerationResponse, LLMProvider

type Clock = Callable[[], datetime]


class ClassificationServiceResult(BaseModel):
    """Provider-neutral result from classifying retained email candidates."""

    model_config = ConfigDict(frozen=True)

    candidate_count: int = Field(ge=0)
    classified_count: int = Field(ge=0)
    malformed_count: int = Field(ge=0)
    classifications: tuple[EmailClassificationRecord, ...]
    malformed: tuple[MalformedLLMExtraction, ...]
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts_and_tokens(self) -> Self:
        if self.classified_count != len(self.classifications):
            raise ValueError("classified_count must match classifications length")
        if self.malformed_count != len(self.malformed):
            raise ValueError("malformed_count must match malformed length")
        if self.classified_count + self.malformed_count > self.candidate_count:
            raise ValueError("result counts cannot exceed candidate_count")
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens cannot be less than prompt plus completion tokens")
        return self


class ClassificationService:
    """Classify retained email candidates through the configured LLM provider."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        llm_provider: LLMProvider,
        clock: Clock | None = None,
    ) -> None:
        self._settings = settings
        self._llm_provider = llm_provider
        self._clock = clock or (lambda: datetime.now(UTC))

    async def classify_candidates(
        self,
        candidates: Sequence[EmailClassificationCandidate],
    ) -> ClassificationServiceResult:
        """Return accepted classifications and public-safe malformed results."""

        classifications: list[EmailClassificationRecord] = []
        malformed: list[MalformedLLMExtraction] = []
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        for candidate in candidates:
            response = await self._llm_provider.generate(
                build_classification_prompt_request(
                    _classification_prompt_email(candidate),
                    prompt_version=self._settings.classification_prompt_version,
                    model=_classification_model(self._settings),
                )
            )
            (
                response_prompt_tokens,
                response_completion_tokens,
                response_total_tokens,
            ) = _usage_tokens(response)
            prompt_tokens += response_prompt_tokens
            completion_tokens += response_completion_tokens
            total_tokens += response_total_tokens

            result = parse_classification_generation_response(
                email_id=candidate.email_id,
                response=response,
                prompt_version=self._settings.classification_prompt_version,
                classified_at=self._clock(),
            )
            if isinstance(result, EmailClassificationRecord):
                classifications.append(result)
            else:
                malformed.append(result)

        return ClassificationServiceResult(
            candidate_count=len(candidates),
            classified_count=len(classifications),
            malformed_count=len(malformed),
            classifications=tuple(classifications),
            malformed=tuple(malformed),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


def _classification_prompt_email(
    candidate: EmailClassificationCandidate,
) -> ClassificationPromptEmail:
    return ClassificationPromptEmail(
        email_id=candidate.email_id,
        from_addr=candidate.from_addr,
        subject=candidate.subject,
        sent_at=candidate.sent_at,
        body_text=candidate.body_text,
    )


def _classification_model(settings: AppSettings) -> str | None:
    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return settings.azure_openai_chat_deployment or None
    return settings.ollama_chat_model


def _usage_tokens(response: LLMGenerationResponse) -> tuple[int, int, int]:
    if response.usage is None:
        return 0, 0, 0

    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = max(response.usage.total_tokens, prompt_tokens + completion_tokens)
    return prompt_tokens, completion_tokens, total_tokens
