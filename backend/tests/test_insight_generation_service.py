from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import AppSettings, LLMProviderName
from app.db.repositories import ApplicationRepository, EventRepository, InsightRepository
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMProviderResponseError,
    LLMResponseFormat,
)
from app.services.insights_service import InsightGenerationService, InsightInputBuilder

BACKEND_ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
CITATION_ID = (
    "application:application-rejected|event:event-rejected-rejection|email:email-rejection"
)


def test_insight_generation_service_generates_and_persists_grounded_narrative(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        repository = InsightRepository(connection)
        provider = FakeLLMProvider(
            (
                LLMGenerationResponse(
                    content=(
                        "Rejected applications repeatedly mention Kubernetes experience. "
                        f"[{CITATION_ID}]"
                    ),
                    model="llama3.1",
                    finish_reason=LLMFinishReason.STOP,
                ),
            )
        )
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=repository,
            llm_provider=provider,
            clock=lambda: GENERATED_AT,
        )

        result = asyncio.run(service.generate_insight("why_rejected"))

        cached = repository.get_cached_insight(
            insight_type="why_rejected",
            inputs_hash=result.insight.inputs_hash,
            model="llama3.1",
        )

    assert result.cached is False
    assert result.insight.type == "why_rejected"
    assert result.insight.content == (
        f"Rejected applications repeatedly mention Kubernetes experience. [{CITATION_ID}]"
    )
    assert result.insight.model == "llama3.1"
    assert result.insight.generated_at == GENERATED_AT
    assert cached == result.insight

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.model == "llama3.1"
    assert request.response_format is LLMResponseFormat.TEXT
    assert request.options.temperature == 0.2
    assert request.options.max_output_tokens == 1200
    assert "Never produce authoritative counts" in request.messages[0].content
    assert "Never emit raw SQL" in request.messages[0].content
    assert "Use only the provided citation_id values" in request.messages[0].content

    prompt_payload = json.loads(request.messages[1].content)
    assert prompt_payload["type"] == "why_rejected"
    assert {fact["name"]: fact["value"] for fact in prompt_payload["facts"]} == {
        "total_applications": 1,
        "status_counts": {"rejected": 1},
        "source_counts": {"linkedin": 1},
        "sponsorship_counts": {"unknown": 1},
        "work_mode_counts": {"remote": 1},
        "event_type_counts": {"applied": 1, "rejection": 1},
    }
    assert prompt_payload["evidence"] == [
        {
            "citation_id": CITATION_ID,
            "application_id": "application-rejected",
            "company": "Acme Corp",
            "role_title": "Backend Engineer",
            "application_status": "rejected",
            "source": "linkedin",
            "sponsorship": "unknown",
            "work_mode": "remote",
            "tech_stack": ["Python", "Kubernetes"],
            "event_id": "event-rejected-rejection",
            "email_id": "email-rejection",
            "event_type": "rejection",
            "event_at": "2026-07-04T10:00:00Z",
            "extract_note": "Rejection mentioned Kubernetes experience.",
            "email_subject": "Update on your application",
            "email_from": "jobs@example.test",
            "email_sent_at": "2026-07-04T10:00:00Z",
            "email_body_text": (
                "Unfortunately, we moved forward with candidates who had more Kubernetes "
                "experience."
            ),
        }
    ]


def test_insight_generation_service_allows_bracketed_non_citation_prose(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        repository = InsightRepository(connection)
        provider = FakeLLMProvider(
            (
                LLMGenerationResponse(
                    content=(
                        f"Focus on Kubernetes [especially production experience]. [{CITATION_ID}]"
                    ),
                    model="llama3.1",
                    finish_reason=LLMFinishReason.STOP,
                ),
            )
        )
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=repository,
            llm_provider=provider,
            clock=lambda: GENERATED_AT,
        )

        result = asyncio.run(service.generate_insight("why_rejected"))

    assert result.insight.content == (
        f"Focus on Kubernetes [especially production experience]. [{CITATION_ID}]"
    )


@pytest.mark.parametrize(
    "content",
    (
        f"[{CITATION_ID}] Rejected applications mention Kubernetes experience.",
        f"According to [{CITATION_ID}], rejected applications mention Kubernetes experience.",
    ),
)
def test_insight_generation_service_accepts_claims_with_same_sentence_citations(
    tmp_path: Path,
    content: str,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=InsightRepository(connection),
            llm_provider=FakeLLMProvider(
                (
                    LLMGenerationResponse(
                        content=content,
                        model="llama3.1",
                        finish_reason=LLMFinishReason.STOP,
                    ),
                ),
            ),
            clock=lambda: GENERATED_AT,
        )

        result = asyncio.run(service.generate_insight("why_rejected"))

    assert result.insight.content == content


def test_insight_generation_service_uses_fresh_cache_without_calling_provider(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        repository = InsightRepository(connection)
        insight_input = InsightInputBuilder(repository).build("why_rejected")
        cached = repository.save_generated_insight(
            insight_type="why_rejected",
            content=f"Cached rejection theme. [{CITATION_ID}]",
            inputs_hash=insight_input.inputs_hash,
            model="llama3.1",
            generated_at=GENERATED_AT,
        )
        provider = FakeLLMProvider(())
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=repository,
            llm_provider=provider,
            clock=lambda: GENERATED_AT,
        )

        result = asyncio.run(service.generate_insight("why_rejected"))

    assert result.cached is True
    assert result.insight == cached
    assert result.input.inputs_hash == insight_input.inputs_hash
    assert provider.requests == []


def test_insight_generation_service_force_regenerate_bypasses_cache(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        repository = InsightRepository(connection)
        insight_input = InsightInputBuilder(repository).build("why_rejected")
        repository.save_generated_insight(
            insight_type="why_rejected",
            content=f"Cached rejection theme. [{CITATION_ID}]",
            inputs_hash=insight_input.inputs_hash,
            model="llama3.1",
            generated_at=GENERATED_AT,
        )
        provider = FakeLLMProvider(
            (
                LLMGenerationResponse(
                    content=f"Regenerated rejection theme. [{CITATION_ID}]",
                    model="llama3.1",
                    finish_reason=LLMFinishReason.STOP,
                ),
            )
        )
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=repository,
            llm_provider=provider,
            clock=lambda: GENERATED_AT,
        )

        result = asyncio.run(service.generate_insight("why_rejected", force=True))

    assert result.cached is False
    assert result.insight.content == f"Regenerated rejection theme. [{CITATION_ID}]"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "response",
    (
        LLMGenerationResponse(
            content="Useful but truncated.",
            model="llama3.1",
            finish_reason=LLMFinishReason.LENGTH,
        ),
        LLMGenerationResponse(
            content="   ",
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
    ),
)
def test_insight_generation_service_rejects_invalid_provider_output(
    tmp_path: Path,
    response: LLMGenerationResponse,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=InsightRepository(connection),
            llm_provider=FakeLLMProvider((response,)),
            clock=lambda: GENERATED_AT,
        )

        with pytest.raises(
            LLMProviderResponseError,
            match="LLM returned invalid insight content.",
        ):
            asyncio.run(service.generate_insight("why_rejected"))


@pytest.mark.parametrize(
    "content",
    (
        "Rejected applications repeatedly mention Kubernetes experience.",
        "Rejected applications repeatedly mention Kubernetes experience. [application:missing]",
        (
            "Rejected applications repeatedly mention Kubernetes experience. "
            f"[{CITATION_ID}] [source-999]"
        ),
        (f"Rejected applications repeatedly mention Kubernetes experience. [{CITATION_ID}] [1]"),
        (
            "Rejected applications repeatedly mention Kubernetes experience. "
            f"[{CITATION_ID}] Your salary target is too high."
        ),
        (
            "Your salary target is too high. "
            f"Rejected applications mention Kubernetes experience [{CITATION_ID}]."
        ),
    ),
)
def test_insight_generation_service_rejects_ungrounded_provider_output(
    tmp_path: Path,
    content: str,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        repository = InsightRepository(connection)
        service = InsightGenerationService(
            settings=insight_settings(),
            insight_repository=repository,
            llm_provider=FakeLLMProvider(
                (
                    LLMGenerationResponse(
                        content=content,
                        model="llama3.1",
                        finish_reason=LLMFinishReason.STOP,
                    ),
                ),
            ),
            clock=lambda: GENERATED_AT,
        )

        with pytest.raises(
            LLMProviderResponseError,
            match="LLM returned ungrounded insight content.",
        ):
            asyncio.run(service.generate_insight("why_rejected"))

        cached = repository.get_latest_insight("why_rejected", include_stale=True)

    assert cached is None


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def insight_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
    )


def insert_rejected_application_fixture(connection: sqlite3.Connection) -> None:
    insert_raw_email(
        connection,
        email_id="email-applied",
        subject="Application received",
        body_text="Thanks for applying to Acme Corp.",
        sent_at="2026-07-01T09:00:00+00:00",
    )
    insert_raw_email(
        connection,
        email_id="email-rejection",
        subject="Update on your application",
        body_text=(
            "Unfortunately, we moved forward with candidates who had more Kubernetes experience."
        ),
        sent_at="2026-07-04T10:00:00+00:00",
    )
    ApplicationRepository(connection).upsert_application(
        id="application-rejected",
        company="Acme Corp",
        role_title="Backend Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="rejected",
        last_activity_at="2026-07-04T10:00:00+00:00",
        created_at="2026-07-01T09:00:00+00:00",
        updated_at="2026-07-04T10:00:00+00:00",
        salary_min=None,
        salary_max=None,
        currency=None,
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=["Python", "Kubernetes"],
    )
    event_repository = EventRepository(connection)
    event_repository.upsert_event(
        id="event-rejected-applied",
        application_id="application-rejected",
        email_id="email-applied",
        event_type="applied",
        event_at="2026-07-01T09:00:00+00:00",
        extract_note="Application confirmation received.",
    )
    event_repository.upsert_event(
        id="event-rejected-rejection",
        application_id="application-rejected",
        email_id="email-rejection",
        event_type="rejection",
        event_at="2026-07-04T10:00:00+00:00",
        extract_note="Rejection mentioned Kubernetes experience.",
    )
    connection.commit()


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    subject: str,
    body_text: str,
    sent_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            "thread-42",
            "jobs@example.test",
            "applicant@example.test",
            subject,
            sent_at,
            body_text,
            "retained",
            "[]",
            "gmail",
            sent_at,
        ),
    )
    connection.commit()


class FakeLLMProvider:
    provider_name = LLMProviderName.OLLAMA.value

    def __init__(self, responses: tuple[LLMGenerationResponse, ...]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMGenerationRequest] = []

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeLLMProvider received an unexpected generation request")
        return self._responses.pop(0)

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
