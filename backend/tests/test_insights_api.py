from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.api.dependencies import get_llm_provider
from app.config import AppSettings, LLMProviderName, get_settings
from app.db.repositories import ApplicationRepository, EventRepository, InsightRepository
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
GENERATED_AT = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
CITATION_ID = (
    "application:application-rejected|event:event-rejected-rejection|email:email-rejection"
)


def test_get_insights_returns_latest_cached_records_in_stable_order(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = InsightRepository(connection)
        repository.save_generated_insight(
            insight_type="weekly_actions",
            content="Follow up with live applications.",
            inputs_hash="weekly-hash",
            model="llama3.1",
            generated_at=GENERATED_AT,
        )
        stale = repository.save_generated_insight(
            insight_type="why_rejected",
            content="Rejections cite Kubernetes experience.",
            inputs_hash="rejected-hash",
            model="llama3.1",
            generated_at=GENERATED_AT,
        )
        connection.execute("UPDATE insights SET is_stale = 1 WHERE id = ?", (stale.id,))
        connection.commit()

    client = create_test_client(database_path)

    response = client.get("/insights")

    assert response.status_code == 200
    records = response.json()
    assert [record["type"] for record in records] == ["why_rejected", "weekly_actions"]
    assert records[0] == {
        "id": stale.id,
        "type": "why_rejected",
        "content": "Rejections cite Kubernetes experience.",
        "inputs_hash": "rejected-hash",
        "is_stale": True,
        "model": "llama3.1",
        "generated_at": "2026-07-06T12:00:00Z",
    }


def test_post_insights_regenerate_forces_generation_and_persists_result(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)

    provider = FakeLLMProvider(
        (
            LLMGenerationResponse(
                content=f"Regenerated rejection theme. [{CITATION_ID}]",
                model="llama3.1",
                finish_reason=LLMFinishReason.STOP,
            ),
        ),
    )
    client = create_test_client(database_path, provider=provider)

    response = client.post("/insights/regenerate", json={"type": "why_rejected"})

    assert response.status_code == 200
    data = response.json()
    assert data["cached"] is False
    assert data["insight"]["type"] == "why_rejected"
    assert data["insight"]["content"] == f"Regenerated rejection theme. [{CITATION_ID}]"
    assert data["insight"]["is_stale"] is False
    assert data["insight"]["model"] == "llama3.1"
    assert len(provider.requests) == 1

    with sqlite3.connect(database_path) as connection:
        stored = InsightRepository(connection).get_latest_insight(
            "why_rejected",
            include_stale=True,
        )

    assert stored is not None
    assert stored.content == f"Regenerated rejection theme. [{CITATION_ID}]"


def test_insights_endpoints_are_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    list_operation = paths["/insights"]["get"]
    assert (
        list_operation["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/InsightRecord"
    )

    regenerate_operation = paths["/insights/regenerate"]["post"]
    assert (
        regenerate_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/InsightRegenerateRequest"
    )
    assert (
        regenerate_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/InsightRegenerateResponse"
    )
    assert (
        regenerate_operation["responses"]["502"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ApiErrorResponse"
    )
    assert (
        regenerate_operation["responses"]["503"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ApiErrorResponse"
    )


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def create_test_client(
    database_path: Path,
    *,
    provider: FakeLLMProvider | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
    )
    if provider is not None:
        app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


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
