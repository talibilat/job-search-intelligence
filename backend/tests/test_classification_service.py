from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from app.config import AppSettings, ClassificationMode, LLMProviderName
from app.models import EmailClassificationCandidate, JobEmailCategory
from app.pipeline.classify import MalformedLLMExtractionReason
from app.providers.llm import (
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMResponseFormat,
    LLMTokenUsage,
)
from app.services.classification import ClassificationService

SENT_AT = datetime(2026, 7, 5, 11, 30, tzinfo=UTC)
CLASSIFIED_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_classification_service_classifies_candidates_with_configured_prompt() -> None:
    provider = FakeLLMProvider(
        (
            LLMGenerationResponse(
                content=json.dumps(valid_prompt_output()),
                model="llama3.1",
                finish_reason=LLMFinishReason.STOP,
                usage=LLMTokenUsage(prompt_tokens=20, completion_tokens=7, total_tokens=27),
            ),
        )
    )
    service = ClassificationService(
        settings=classification_settings(),
        llm_provider=provider,
        clock=lambda: CLASSIFIED_AT,
    )

    result = asyncio.run(service.classify_candidates((classification_candidate(),)))

    assert result.candidate_count == 1
    assert result.classified_count == 1
    assert result.malformed_count == 0
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 7
    assert result.total_tokens == 27
    assert result.malformed == ()
    assert len(result.accepted) == 1

    classification = result.classifications[0]
    assert classification.email_id == "email-1"
    assert classification.is_job_related is True
    assert classification.category is JobEmailCategory.APPLICATION_CONFIRMATION
    assert classification.confidence == 0.97
    assert classification.model == "llama3.1"
    assert classification.prompt_version == "classification-service-v2"
    assert classification.classified_at == CLASSIFIED_AT
    extraction = result.accepted[0].extraction
    assert extraction.company == "Example Systems"
    assert extraction.role_title == "Backend Engineer"
    assert extraction.status == "applied"
    assert extraction.event_type == "applied"
    assert extraction.tech_stack == ["Python", "FastAPI"]

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.model == "llama3.1"
    assert request.response_format is LLMResponseFormat.JSON_OBJECT
    assert request.options.temperature == 0
    assert "Prompt version: classification-service-v2" in request.messages[0].content
    request_payload = json.loads(request.messages[1].content)
    assert request_payload == {
        "email_id": "email-1",
        "from_addr": "jobs@example.test",
        "subject": "Application received",
        "sent_at": "2026-07-05T11:30:00Z",
        "body_text": "Thanks for applying to the Backend Engineer role.",
    }


def test_classification_service_quarantines_malformed_output() -> None:
    provider = FakeLLMProvider(
        (
            LLMGenerationResponse(
                content=json.dumps(valid_prompt_output() | {"raw_sql": "select * from raw_emails"}),
                model="llama3.1",
                finish_reason=LLMFinishReason.STOP,
            ),
        )
    )
    service = ClassificationService(
        settings=classification_settings(),
        llm_provider=provider,
        clock=lambda: CLASSIFIED_AT,
    )

    result = asyncio.run(service.classify_candidates((classification_candidate(),)))

    assert result.candidate_count == 1
    assert result.classified_count == 0
    assert result.malformed_count == 1
    assert result.classifications == ()
    assert result.accepted == ()

    malformed = result.malformed[0]
    assert malformed.email_id == "email-1"
    assert malformed.model == "llama3.1"
    assert malformed.prompt_version == "classification-service-v2"
    assert malformed.reason is MalformedLLMExtractionReason.INVALID_SCHEMA
    assert "raw_sql" not in repr(malformed)
    assert "select *" not in repr(malformed)


def classification_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        classification_mode=ClassificationMode.LOCAL,
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
        classification_prompt_version="classification-service-v2",
    )


def classification_candidate() -> EmailClassificationCandidate:
    return EmailClassificationCandidate(
        email_id="email-1",
        from_addr="jobs@example.test",
        subject="Application received",
        sent_at=SENT_AT,
        body_text="Thanks for applying to the Backend Engineer role.",
    )


def valid_prompt_output() -> dict[str, object]:
    return {
        "is_job_related": True,
        "category": "application_confirmation",
        "confidence": 0.97,
        "company": "Example Systems",
        "role_title": "Backend Engineer",
        "application_status": "applied",
        "event_type": "applied",
        "event_at": "2026-07-05T11:30:00Z",
        "salary_min": None,
        "salary_max": None,
        "currency": None,
        "location": "Remote",
        "work_mode": "remote",
        "seniority": "senior",
        "sponsorship": "unknown",
        "tech_stack": ["Python", "FastAPI"],
        "rejection_reason": None,
    }


class FakeLLMProvider:
    provider_name = LLMProviderName.OLLAMA.value

    def __init__(self, responses: tuple[LLMGenerationResponse, ...]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMGenerationRequest] = []

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        self.requests.append(request)
        return self._responses.pop(0)

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        raise NotImplementedError

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        return LLMProviderHealthCheckResponse(
            provider_name=self.provider_name,
            status=LLMModelHealthStatus.AVAILABLE,
            checks=(
                LLMModelHealthCheck(
                    kind=LLMModelKind.CHAT,
                    model=request.chat_model,
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
                LLMModelHealthCheck(
                    kind=LLMModelKind.EMBEDDING,
                    model=request.embedding_model,
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
            ),
        )
