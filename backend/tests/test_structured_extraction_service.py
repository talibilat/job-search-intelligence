from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import AppSettings, ClassificationMode, LLMProviderName
from app.db.repositories import ClassificationRunRepository, EmailRepository
from app.models import ClassificationRunRecord
from app.providers.llm import (
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMTokenUsage,
)
from app.services.structured_extraction import StructuredExtractionService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_structured_extraction_service_stores_only_accepted_classifications(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "accepted-email", body_text="Your application was rejected.")
    insert_raw_email(connection, "malformed-email", body_text="We received your application.")
    insert_raw_email(connection, "metadata-only", body_text=None, retention_state="metadata_only")
    insert_raw_email(connection, "current-email", body_text="Already processed.")
    insert_classification(connection, "current-email", model="llama3.1", prompt_version="v2")
    connection.commit()
    provider = FakeLLMProvider(
        responses=(
            LLMGenerationResponse(
                content=valid_structured_response_json(),
                model="llama3.1",
                finish_reason=LLMFinishReason.STOP,
                usage=LLMTokenUsage(prompt_tokens=20, completion_tokens=8, total_tokens=28),
            ),
            LLMGenerationResponse(
                content="{not-json",
                model="llama3.1",
                finish_reason=LLMFinishReason.STOP,
                usage=LLMTokenUsage(prompt_tokens=15, completion_tokens=3, total_tokens=18),
            ),
        ),
    )
    service = StructuredExtractionService(
        settings=AppSettings(
            _env_file=None,
            classification_mode=ClassificationMode.LOCAL,
            llm_provider=LLMProviderName.OLLAMA,
            ollama_chat_model="llama3.1",
            classification_prompt_version="v2",
            classification_batch_size=10,
        ),
        email_repository=EmailRepository(connection),
        classification_run_repository=ClassificationRunRepository(connection),
        llm_provider=provider,
        clock=lambda: NOW,
        run_id_factory=lambda: "run-1",
    )

    result = asyncio.run(service.run_batch())

    request_payloads = [request.messages[1].content for request in provider.requests]
    stored_classifications = [
        tuple(row)
        for row in connection.execute(
            """
            SELECT
                email_id,
                is_job_related,
                category,
                confidence,
                model,
                prompt_version,
                classified_at
            FROM email_classifications
            ORDER BY email_id
            """,
        ).fetchall()
    ]
    stored_run = ClassificationRunRepository(connection).fetch_run("run-1")
    assert len(provider.requests) == 2
    assert "accepted-email" in request_payloads[0]
    assert "malformed-email" in request_payloads[1]
    assert stored_classifications == [
        ("accepted-email", 1, "rejection", 0.92, "llama3.1", "v2", NOW.isoformat()),
        ("current-email", 1, "application_confirmation", 0.98, "llama3.1", "v2", NOW.isoformat()),
    ]
    assert result.run_record.candidate_count == 2
    assert result.run_record.classified_count == 1
    assert result.run_record.prompt_tokens == 35
    assert result.run_record.completion_tokens == 11
    assert result.run_record.total_tokens == 46
    assert result.run_record.estimated_cost_usd == 0
    assert stored_run == result.run_record
    assert result.accepted_results[0].classification.email_id == "accepted-email"
    assert result.accepted_results[0].extraction.company == "Example Systems"
    assert result.accepted_results[0].extraction.role_title == "Backend Engineer"
    assert result.accepted_results[0].extraction.event_type == "rejection"
    assert result.malformed_results[0].email_id == "malformed-email"
    assert "not-json" not in repr(result.malformed_results[0])


def test_structured_extraction_service_rolls_back_classifications_when_run_accounting_fails(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "accepted-email", body_text="Your application was rejected.")
    connection.commit()
    service = StructuredExtractionService(
        settings=AppSettings(
            _env_file=None,
            classification_mode=ClassificationMode.LOCAL,
            llm_provider=LLMProviderName.OLLAMA,
            ollama_chat_model="llama3.1",
            classification_prompt_version="v2",
            classification_batch_size=10,
        ),
        email_repository=EmailRepository(connection),
        classification_run_repository=FailingClassificationRunRepository(connection),
        llm_provider=FakeLLMProvider(
            responses=(
                LLMGenerationResponse(
                    content=valid_structured_response_json(),
                    model="llama3.1",
                    finish_reason=LLMFinishReason.STOP,
                ),
            ),
        ),
        clock=lambda: NOW,
        run_id_factory=lambda: "run-1",
    )

    with pytest.raises(RuntimeError, match="run accounting failed"):
        asyncio.run(service.run_batch())

    stored_classification_count = connection.execute(
        "SELECT COUNT(*) FROM email_classifications WHERE email_id = ?",
        ("accepted-email",),
    ).fetchone()
    stored_run_count = connection.execute(
        "SELECT COUNT(*) FROM classification_runs WHERE id = ?",
        ("run-1",),
    ).fetchone()
    assert stored_classification_count is not None
    assert stored_classification_count[0] == 0
    assert stored_run_count is not None
    assert stored_run_count[0] == 0


class FakeLLMProvider:
    provider_name = "ollama"

    def __init__(self, *, responses: tuple[LLMGenerationResponse, ...]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMGenerationRequest] = []

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("unexpected LLM request")
        return self._responses.pop(0)

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        raise NotImplementedError

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        raise NotImplementedError


class FailingClassificationRunRepository(ClassificationRunRepository):
    def upsert_run(self, record: ClassificationRunRecord) -> None:
        raise RuntimeError("run accounting failed")


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    body_text: str | None,
    retention_state: str = "retained",
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id,
            thread_id,
            from_addr,
            to_addr,
            subject,
            sent_at,
            body_text,
            body_retention_state,
            labels,
            provider,
            ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "me@example.test",
            "Application update",
            NOW.isoformat(),
            body_text,
            retention_state,
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def insert_classification(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    model: str,
    prompt_version: str,
) -> None:
    connection.execute(
        """
        INSERT INTO email_classifications (
            email_id,
            is_job_related,
            category,
            confidence,
            model,
            prompt_version,
            classified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            1,
            "application_confirmation",
            0.98,
            model,
            prompt_version,
            NOW.isoformat(),
        ),
    )


def valid_structured_response_json() -> str:
    return (
        "{"
        '"is_job_related":true,'
        '"category":"rejection",'
        '"confidence":0.92,'
        '"company":"Example Systems",'
        '"role_title":"Backend Engineer",'
        '"application_status":"rejected",'
        '"event_type":"rejection",'
        '"event_at":"2026-07-04T12:30:00+00:00",'
        '"salary_min":120000,'
        '"salary_max":150000,'
        '"currency":"USD",'
        '"location":"Remote",'
        '"work_mode":"remote",'
        '"seniority":"senior",'
        '"sponsorship":"unknown",'
        '"tech_stack":["Python","FastAPI"],'
        '"rejection_reason":"The role was filled."'
        "}"
    )
