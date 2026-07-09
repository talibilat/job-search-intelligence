from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.api.dependencies import get_structured_extraction_service
from app.config import AppSettings, ClassificationMode, LLMProviderName, get_settings
from app.db.repositories import ClassificationRunRepository, EmailRepository
from app.main import create_app
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
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_post_classification_run_classifies_and_persists(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "email-1", body_text="Your application was rejected.")
        insert_raw_email(connection, "email-2", body_text="We received your application.")

    service = _make_fake_service(database_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        classification_mode=ClassificationMode.LOCAL,
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
        classification_prompt_version="v2",
        classification_batch_size=10,
    )
    app.dependency_overrides[get_structured_extraction_service] = lambda: service
    client = TestClient(app)

    response = client.post("/classification/run")

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "test-run-1"
    assert data["provider"] == "ollama"
    assert data["model"] == "llama3.1"
    assert data["prompt_version"] == "v2"
    assert data["candidate_count"] == 2
    assert data["classified_count"] == 1
    assert data["malformed_count"] == 1
    assert data["prompt_tokens"] == 35
    assert data["completion_tokens"] == 11
    assert data["total_tokens"] == 46
    assert data["estimated_cost_usd"] == 0
    assert data["classification_mode"] == "local"
    assert data["llm_provider"] == "ollama"
    assert data["started_at"] is not None
    assert data["completed_at"] is not None
    assert data["applications_upserted"] == 1
    assert data["events_upserted"] == 1
    assert data["skipped_not_job_related"] == 0
    assert data["manual_conflict_count"] == 0

    with sqlite3.connect(database_path) as connection:
        stored = connection.execute(
            "SELECT email_id, is_job_related, category, model, prompt_version "
            "FROM email_classifications ORDER BY email_id",
        ).fetchall()
        assert len(stored) == 1
        assert stored[0] == ("email-1", 1, "rejection", "llama3.1", "v2")

        run_count = connection.execute(
            "SELECT COUNT(*) FROM classification_runs WHERE id = ?",
            ("test-run-1",),
        ).fetchone()
        assert run_count is not None
        assert run_count[0] == 1

        applications = connection.execute(
            "SELECT company, role_title, current_status FROM applications",
        ).fetchall()
        assert applications == [("Example Systems", "Backend Engineer", "rejected")]

        events = connection.execute(
            "SELECT email_id, event_type FROM application_events",
        ).fetchall()
        assert events == [("email-1", "rejection")]


def test_post_classification_run_returns_empty_run_when_no_candidates(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)

    service = _make_fake_service(database_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        classification_mode=ClassificationMode.LOCAL,
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
        classification_prompt_version="v2",
        classification_batch_size=10,
    )
    app.dependency_overrides[get_structured_extraction_service] = lambda: service
    client = TestClient(app)

    response = client.post("/classification/run")

    assert response.status_code == 200
    data = response.json()
    assert data["candidate_count"] == 0
    assert data["classified_count"] == 0
    assert data["malformed_count"] == 0
    assert data["prompt_tokens"] == 0
    assert data["completion_tokens"] == 0
    assert data["total_tokens"] == 0


def test_post_classification_run_returns_error_on_llm_failure(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "failing-email", body_text="Application update.")

    service = _make_fake_service_with_failing_llm(database_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        classification_mode=ClassificationMode.LOCAL,
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
        classification_prompt_version="v2",
        classification_batch_size=10,
    )
    app.dependency_overrides[get_structured_extraction_service] = lambda: service
    client = TestClient(app)

    response = client.post("/classification/run")

    assert response.status_code == 200
    data = response.json()
    assert data["candidate_count"] == 1
    assert data["classified_count"] == 0
    assert data["malformed_count"] == 1
    assert data["malformed_count"] == 1


def _make_fake_service(database_path: Path) -> StructuredExtractionService:
    connection = sqlite3.connect(database_path, check_same_thread=False)
    return StructuredExtractionService(
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
        llm_provider=_FakeLLMProvider(
            responses=(
                LLMGenerationResponse(
                    content=(
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
                    ),
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
        ),
        clock=lambda: NOW,
        run_id_factory=lambda: "test-run-1",
    )


def _make_fake_service_with_failing_llm(database_path: Path) -> StructuredExtractionService:
    connection = sqlite3.connect(database_path, check_same_thread=False)
    return StructuredExtractionService(
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
        llm_provider=_FakeLLMProvider(
            responses=(
                LLMGenerationResponse(
                    content="not valid json at all",
                    model="llama3.1",
                    finish_reason=LLMFinishReason.STOP,
                ),
            ),
        ),
        clock=lambda: NOW,
        run_id_factory=lambda: "test-run-2",
    )


def create_classification_tables(database_path: Path) -> None:
    """Create the full migrated schema so classification and aggregation both work."""

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    body_text: str | None,
    body_retention_state: str = "retained",
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
            body_retention_state,
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


class _FakeLLMProvider:
    provider_name = "ollama"

    def __init__(self, *, responses: tuple[LLMGenerationResponse, ...]) -> None:
        self._responses = list(responses)

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
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
