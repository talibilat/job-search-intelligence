from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, LLMProviderName, get_settings
from app.db.repositories import ApplicationRepository, EventRepository
from app.main import create_app
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
)
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_get_insights_returns_cached_recurring_feedback(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    generated_at = "2026-07-07T12:00:00+00:00"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO insights (
                type,
                content,
                inputs_hash,
                is_stale,
                model,
                generated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "recurring_feedback",
                "Feedback repeatedly says to sharpen system design examples. "
                "[application:app-1|event:event-1|email:email-1]",
                "inputs-hash",
                0,
                "llama3.1",
                generated_at,
            ),
        )
        connection.commit()

    client = create_test_client(database_path)

    response = client.get("/insights")

    assert response.status_code == 200
    assert response.json() == {
        "insights": [
            {
                "id": 1,
                "type": "recurring_feedback",
                "content": (
                    "Feedback repeatedly says to sharpen system design examples. "
                    "[application:app-1|event:event-1|email:email-1]"
                ),
                "inputs_hash": "inputs-hash",
                "is_stale": False,
                "model": "llama3.1",
                "generated_at": "2026-07-07T12:00:00Z",
            },
        ],
    }


def test_post_insights_regenerate_answers_q41(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_feedback_fixture(connection)

    provider = FakeLLMProvider(
        (
            LLMGenerationResponse(
                content=(
                    "Feedback consistently says to improve system design examples. "
                    "[application:app-1|event:event-1|email:email-1]"
                ),
                model="llama3.1",
                finish_reason=LLMFinishReason.STOP,
            ),
        ),
    )
    client = create_test_client(database_path, provider=provider)

    response = client.post(
        "/insights/regenerate",
        json={"type": "recurring_feedback", "max_evidence_items": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["insight"]["type"] == "recurring_feedback"
    assert body["insight"]["content"] == (
        "Feedback consistently says to improve system design examples. "
        "[application:app-1|event:event-1|email:email-1]"
    )
    assert body["evidence_citation_ids"] == [
        "application:app-1|event:event-1|email:email-1",
        "application:app-1|event:event-2|email:email-2",
    ]
    assert len(provider.requests) == 1


def create_test_client(
    database_path: Path,
    *,
    provider: FakeLLMProvider | None = None,
) -> TestClient:
    app = create_app(
        settings=AppSettings(
            _env_file=None,
            database_url=f"sqlite+aiosqlite:///{database_path}",
            llm_provider=LLMProviderName.OLLAMA,
            ollama_chat_model="llama3.1",
        ),
    )
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
    )
    if provider is not None:
        from app.api.dependencies import get_llm_provider

        app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def insert_feedback_fixture(connection: sqlite3.Connection) -> None:
    insert_raw_email(
        connection,
        email_id="email-1",
        subject="Interview feedback",
        body_text="Please improve system design examples.",
        sent_at="2026-07-05T10:00:00+00:00",
    )
    insert_raw_email(
        connection,
        email_id="email-2",
        subject="More interview feedback",
        body_text="More concrete system design examples would help.",
        sent_at="2026-07-06T10:00:00+00:00",
    )
    ApplicationRepository(connection).upsert_application(
        id="app-1",
        company="Acme Corp",
        role_title="Backend Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="rejected",
        last_activity_at="2026-07-06T10:00:00+00:00",
        created_at="2026-07-01T09:00:00+00:00",
        updated_at="2026-07-06T10:00:00+00:00",
        salary_min=None,
        salary_max=None,
        currency=None,
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=["Python"],
    )
    event_repository = EventRepository(connection)
    event_repository.upsert_event(
        id="event-1",
        application_id="app-1",
        email_id="email-1",
        event_type="feedback",
        event_at="2026-07-05T10:00:00+00:00",
        extract_note="Feedback said to improve system design examples.",
    )
    event_repository.upsert_event(
        id="event-2",
        application_id="app-1",
        email_id="email-2",
        event_type="feedback",
        event_at="2026-07-06T10:00:00+00:00",
        extract_note="Feedback again mentioned system design examples.",
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
