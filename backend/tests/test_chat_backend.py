from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.api.dependencies import get_llm_provider
from app.config import AppSettings, get_settings
from app.db.engine import load_sqlite_vec_sync
from app.db.repositories import ApplicationRepository
from app.main import create_app
from app.providers.llm import (
    LLMEmbedding,
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMGenerationRequest,
    LLMProviderHealthCheckRequest,
)
from app.security import SecretRef, SecretStore
from app.services.chat_service import route_question
from app.services.wipe_data import wipe_local_data
from fastapi.testclient import TestClient
from pydantic import SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class FakeChatProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.embedding_inputs: list[tuple[str, ...]] = []

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        self.embedding_inputs.append(request.inputs)
        return LLMEmbeddingResponse(
            model=request.model or "fake-embedding",
            embeddings=tuple(
                LLMEmbedding(index=index, embedding=_embedding_for_text(text))
                for index, text in enumerate(request.inputs)
            ),
        )

    async def generate(self, request: LLMGenerationRequest) -> None:
        raise AssertionError(f"chat must not ask an LLM to restate tool facts: {request!r}")

    async def health_check(self, request: LLMProviderHealthCheckRequest) -> None:
        raise AssertionError(f"chat request must not perform a readiness probe: {request!r}")


class EmptySecretStore(SecretStore):
    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        return None

    async def delete_secret(self, ref: SecretRef) -> None:
        return None


@pytest.mark.parametrize(
    ("question", "expected"),
    (
        ("What exactly did the recruiter at Acme say?", "content"),
        ("Show me every rejection email that mentioned experience", "content"),
        ("Who am I waiting on and who is overdue for a follow-up?", "quantitative"),
        ("How many applications and what exactly did recruiters say?", "mixed"),
        ("Tell me anything useful about my Acme search", "content"),
    ),
)
def test_q47_to_q50_representative_questions_route_without_sql(
    question: str,
    expected: str,
) -> None:
    assert route_question(question) == expected


def test_chat_api_reconciles_metrics_retrieves_citations_and_persists_history(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    metric_response = client.get("/metrics/summary")
    quantitative = client.post(
        "/chat",
        json={"conversation_id": "q-count", "message": "How many jobs have I applied to?"},
    )

    assert metric_response.status_code == 200
    assert quantitative.status_code == 200
    quantitative_body = quantitative.json()
    assert quantitative_body["route"] == "quantitative"
    assert quantitative_body["tool_outputs"][0]["template"] == "summary_counts"
    assert (
        quantitative_body["tool_outputs"][0]["rows"][0]["values"]["total_applications"]
        == metric_response.json()["total_applications"]
    )
    assert quantitative_body["citations"] == [
        {
            "citation_id": "metric:summary_counts",
            "source": "metric",
            "email_public_id": None,
            "application_id": None,
            "metric_template": "summary_counts",
            "subject": None,
            "sent_at": None,
            "snippet": None,
        }
    ]
    assert [increment["type"] for increment in quantitative_body["increments"]] == [
        "route",
        "tool",
        "answer",
    ]
    assert provider.embedding_inputs == []

    content = client.post(
        "/chat",
        json={
            "conversation_id": "q-content",
            "message": "What exactly did the recruiter at Acme say in the last email?",
        },
    )

    assert content.status_code == 200
    content_body = content.json()
    assert content_body["route"] == "content"
    assert "Technical interview moved to Friday" in content_body["answer"]
    assert content_body["citations"][0]["source"] == "email"
    assert content_body["citations"][0]["application_id"] == "app-acme"
    assert content_body["citations"][0]["email_public_id"]
    assert content_body["citations"][0]["citation_id"].startswith("email:")
    with sqlite3.connect(database_path) as connection:
        load_sqlite_vec_sync(connection, None)
        assert connection.execute("SELECT DISTINCT email_id FROM email_chunks").fetchall() == [
            ("email-job",)
        ]
    embedded_body_batches = [inputs for inputs in provider.embedding_inputs if len(inputs) > 1]
    assert embedded_body_batches == []
    assert any(
        inputs == ("Acme recruiter: Technical interview moved to Friday.",)
        for inputs in provider.embedding_inputs
    )
    embedded_texts = [text for batch in provider.embedding_inputs for text in batch]
    assert all("private shopping receipt" not in text for text in embedded_texts)
    assert all("debug-only body" not in text for text in embedded_texts)

    mixed = client.post(
        "/chat",
        json={
            "conversation_id": "q-mixed",
            "message": "How many applications and what exactly did the Acme recruiter say?",
        },
    )

    assert mixed.status_code == 200
    assert mixed.json()["route"] == "mixed"
    assert [output["tool"] for output in mixed.json()["tool_outputs"]] == [
        "structured_query",
        "semantic_search",
    ]
    assert {citation["source"] for citation in mixed.json()["citations"]} == {
        "metric",
        "email",
    }
    assert (
        provider.embedding_inputs.count(("Acme recruiter: Technical interview moved to Friday.",))
        == 1
    )

    waiting = client.post(
        "/chat",
        json={
            "conversation_id": "q-waiting",
            "message": "Who am I waiting on and who is overdue for a follow-up?",
        },
    )
    assert waiting.status_code == 200
    assert waiting.json()["tool_outputs"][0]["template"] == "live_applications"
    assert waiting.json()["citations"][0] == {
        "citation_id": "application:app-acme",
        "source": "application",
        "email_public_id": None,
        "application_id": "app-acme",
        "metric_template": None,
        "subject": None,
        "sent_at": None,
        "snippet": None,
    }

    history = client.get("/chat/history", params={"conversation_id": "q-mixed"})
    assert history.status_code == 200
    assert [message["role"] for message in history.json()["messages"]] == [
        "user",
        "tool",
        "tool",
        "assistant",
    ]
    assistant = history.json()["messages"][-1]
    assert {citation["source"] for citation in assistant["citations_json"]} == {
        "metric",
        "email",
    }
    assert [output["tool"] for output in assistant["tool_outputs_json"]] == [
        "structured_query",
        "semantic_search",
    ]


def test_chat_index_removes_ineligible_vectors_and_refuses_unsupported_content(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)
    first = client.post("/chat", json={"message": "What exactly did Acme say?"})
    assert first.status_code == 200
    assert first.json()["citations"]

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE email_classifications SET is_job_related = 0 WHERE email_id = ?",
            ("email-job",),
        )
        connection.commit()

    refused = client.post("/chat", json={"message": "What exactly did Acme say?"})

    assert refused.status_code == 200
    assert refused.json()["citations"] == []
    assert "cannot answer" in refused.json()["answer"]
    with sqlite3.connect(database_path) as connection:
        load_sqlite_vec_sync(connection, None)
        assert connection.execute("SELECT COUNT(*) FROM email_chunks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM email_chunk_index_state").fetchone()[0] == 0


def test_chat_request_validates_blank_ids_and_openapi_has_incremental_contract(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    invalid = client.post(
        "/chat",
        json={"conversation_id": "   ", "message": "How many applications?"},
    )
    schema = client.get("/openapi.json").json()

    assert invalid.status_code == 422
    operation = schema["paths"]["/chat"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ChatResponse"
    }
    assert schema["components"]["schemas"]["ChatResponse"]["required"] == [
        "conversation_id",
        "route",
        "answer",
        "citations",
        "tool_outputs",
        "increments",
    ]


def test_wipe_removes_persisted_chat_and_embeddings(tmp_path: Path) -> None:
    data_dir = tmp_path / ".jobtracker"
    database_path = migrated_database(data_dir)
    seed_chat_sources(database_path)
    provider = FakeChatProvider()
    with create_chat_client(database_path, provider) as client:
        response = client.post(
            "/chat",
            json={"conversation_id": "wipe-me", "message": "What exactly did Acme say?"},
        )
        assert response.status_code == 200
        assert client.get("/chat/history").json()["messages"]

    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite:///{database_path}",
        fernet_key_file=data_dir / "fernet.key",
    )
    result = asyncio.run(
        wipe_local_data(settings, secret_store=EmptySecretStore(), connection_secret_refs=[])
    )

    assert result.status == "wiped"
    assert not database_path.exists()
    assert not data_dir.exists()


def create_chat_client(database_path: Path, provider: FakeChatProvider) -> TestClient:
    settings = AppSettings(_env_file=None, database_url=f"sqlite:///{database_path}")
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


def migrated_database(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def seed_chat_sources(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(
            connection,
            email_id="email-job",
            subject="Interview update",
            body="Acme recruiter: Technical interview moved to Friday.",
            retention="retained",
        )
        insert_raw_email(
            connection,
            email_id="email-non-job",
            subject="Receipt",
            body="private shopping receipt",
            retention="retained",
        )
        insert_raw_email(
            connection,
            email_id="email-debug",
            subject="Debug",
            body="debug-only body",
            retention="debugging",
        )
        insert_raw_email(
            connection,
            email_id="email-metadata",
            subject="Metadata only",
            body=None,
            retention="metadata_only",
        )
        insert_classification(connection, "email-job", is_job_related=True)
        insert_classification(connection, "email-non-job", is_job_related=False)
        insert_classification(connection, "email-debug", is_job_related=True)
        insert_classification(connection, "email-metadata", is_job_related=True)
        ApplicationRepository(connection).upsert_application(
            id="app-acme",
            company="Acme",
            role_title="Platform Engineer",
            source="company_site",
            first_seen_at="2026-06-01T10:00:00+00:00",
            current_status="in_review",
            salary_min=None,
            salary_max=None,
            currency=None,
            location="Remote",
            work_mode="remote",
            seniority="senior",
            sponsorship="unknown",
            tech_stack=["Python"],
            last_activity_at="2026-06-05T10:00:00+00:00",
            created_at="2026-06-01T10:00:00+00:00",
            updated_at="2026-06-05T10:00:00+00:00",
        )
        connection.execute(
            """
            INSERT INTO application_events (
                id, application_id, email_id, event_type, event_at, extract_note
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "event-acme",
                "app-acme",
                "email-job",
                "response",
                "2026-06-05T10:00:00+00:00",
                "Recruiter response",
            ),
        )
        connection.commit()


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    subject: str,
    body: str | None,
    retention: str,
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
            f"thread-{email_id}",
            "recruiter@example.test",
            "candidate@example.test",
            subject,
            "2026-06-05T10:00:00+00:00",
            body,
            retention,
            "[]",
            "gmail",
            "2026-06-05T10:01:00+00:00",
        ),
    )


def insert_classification(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    is_job_related: bool,
) -> None:
    connection.execute(
        """
        INSERT INTO email_classifications (
            email_id, is_job_related, category, confidence, model, prompt_version, classified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            is_job_related,
            "recruiter_outreach" if is_job_related else "other",
            0.95,
            "fixture-model",
            "v1",
            "2026-06-05T10:02:00+00:00",
        ),
    )


def _embedding_for_text(text: str) -> tuple[float, ...]:
    normalized = text.casefold()
    if "acme" in normalized or "friday" in normalized:
        return (1.0, 0.0)
    return (0.0, 1.0)
