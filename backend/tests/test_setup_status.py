from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.api.dependencies import (
    get_llm_secret_store,
    get_provider_configuration_repository,
)
from app.api.provider_config import get_active_sync_scheduler
from app.config import (
    GMAIL_READONLY_SCOPE,
    AppSettings,
    ClassificationMode,
    EmailProviderName,
    LLMProviderName,
    get_settings,
)
from app.db.repositories import EmailConnectionRepository
from app.main import create_app
from app.providers.email import EmailAccountRef, EmailAddress, EmailConnection
from app.security import GMAIL_OAUTH_CLIENT_REF, SecretKind, SecretRef
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def clear_jobtracker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)


class MemoryProviderConfigRepository:
    def save(self, settings: AppSettings) -> None:
        return None


class NoopScheduler:
    def reconfigure(self, *, sync_on_open: bool, interval_seconds: int) -> None:
        return None


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[SecretRef, SecretStr] = {}

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return self.values.get(ref)

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        self.values[ref] = value

    async def delete_secret(self, ref: SecretRef) -> None:
        self.values.pop(ref, None)


def create_test_app(
    settings: AppSettings,
    secret_store: MemorySecretStore | None = None,
) -> FastAPI:
    fastapi_app = create_app()

    def override_settings() -> AppSettings:
        return settings

    fastapi_app.dependency_overrides[get_settings] = override_settings
    fastapi_app.dependency_overrides[get_provider_configuration_repository] = (
        MemoryProviderConfigRepository
    )
    fastapi_app.dependency_overrides[get_active_sync_scheduler] = NoopScheduler
    fastapi_app.dependency_overrides[get_llm_secret_store] = lambda: (
        secret_store or MemorySecretStore()
    )
    return fastapi_app


def migrate_test_database(database_path: Path) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")


def save_gmail_connection(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        EmailConnectionRepository(connection).save_connection(
            EmailConnection(
                account=EmailAccountRef(
                    provider=EmailProviderName.GMAIL,
                    account_id="me@example.com",
                ),
                display_email=EmailAddress(address="me@example.com"),
                credential_ref=SecretRef(
                    kind=SecretKind.OAUTH_TOKEN,
                    provider="gmail",
                    name="me-example-com",
                ),
                granted_scopes=(GMAIL_READONLY_SCOPE,),
                connected_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
            )
        )


def test_connection_repository_reports_no_default_connection_before_migrations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    with sqlite3.connect(database_path) as connection:
        default_connection = EmailConnectionRepository(
            connection,
        ).fetch_default_connection_metadata(EmailProviderName.GMAIL)

    assert default_connection is None


def test_setup_status_endpoint_returns_phase_zero_shell_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clear_jobtracker_env(monkeypatch)
    # Point at an empty temp database so a developer's real local
    # .jobtracker data cannot leak a Gmail connection into this assertion.
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'jobtracker.sqlite3'}",
    )
    client = TestClient(create_test_app(settings))

    response = client.get("/setup/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["setup_complete"] is False
    assert payload["gmail_connected"] is False
    assert payload["llm_configured"] is False
    assert payload["readiness"]["gmail_sync"]["state"] == "missing_credential"
    assert payload["readiness"]["chat_generation"]["state"] == "unavailable"


def test_setup_status_endpoint_reports_configured_setup_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
    )
    client = TestClient(create_test_app(settings))

    response = client.get("/setup/status")

    assert response.status_code == 200
    assert response.json()["llm_provider"] == "azure_openai"
    assert response.json()["classification_mode"] == "hybrid"
    assert response.json()["recommended_classification_mode"] == "hybrid"


def test_setup_status_endpoint_recommends_hybrid_for_azure_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.LLM,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embeddings",
    )
    client = TestClient(create_test_app(settings))

    response = client.get("/setup/status")

    assert response.status_code == 200
    assert response.json()["classification_mode"] == "llm"
    assert response.json()["recommended_classification_mode"] == "hybrid"


def test_setup_status_endpoint_reports_persisted_gmail_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clear_jobtracker_env(monkeypatch)
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate_test_database(database_path)
    save_gmail_connection(database_path)
    secret_store = MemorySecretStore()
    secret_store.values[GMAIL_OAUTH_CLIENT_REF] = SecretStr("client-json")
    secret_store.values[
        SecretRef(kind=SecretKind.OAUTH_TOKEN, provider="gmail", name="me-example-com")
    ] = SecretStr("token")
    client = TestClient(
        create_test_app(
            AppSettings(
                _env_file=None,
                database_url=f"sqlite+aiosqlite:///{database_path}",
            ),
            secret_store,
        )
    )

    response = client.get("/setup/status")

    assert response.status_code == 200
    assert response.json()["gmail_connected"] is True


def test_setup_status_endpoint_is_documented_in_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/setup/status"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/SetupStatusResponse"


def test_setup_submit_endpoint_accepts_phase_zero_shell_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.post(
        "/setup",
        json={
            "email_provider": "gmail",
            "llm_provider": "ollama",
            "classification_mode": "local",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["setup_complete"] is False
    assert response.json()["readiness"]["chat_generation"]["state"] == "unavailable"


def test_setup_submit_endpoint_preselects_local_mode_for_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.post(
        "/setup",
        json={
            "email_provider": "gmail",
            "llm_provider": "ollama",
        },
    )

    assert response.status_code == 200
    assert response.json()["classification_mode"] == "local"
    assert response.json()["recommended_classification_mode"] == "local"


def test_setup_submit_endpoint_preselects_hybrid_mode_for_azure_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.post(
        "/setup",
        json={
            "email_provider": "gmail",
            "llm_provider": "azure_openai",
            "azure_openai_endpoint": "https://example.openai.azure.com",
            "azure_openai_chat_deployment": "chat",
            "azure_openai_embedding_deployment": "embeddings",
        },
    )

    assert response.status_code == 200
    assert response.json()["classification_mode"] == "hybrid"
    assert response.json()["recommended_classification_mode"] == "hybrid"


def test_setup_submit_endpoint_rejects_incomplete_selected_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.post(
        "/setup",
        json={
            "email_provider": "gmail",
            "llm_provider": "azure_openai",
            "classification_mode": "hybrid",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Submitted setup choices are incomplete.",
            "details": [
                {
                    "field": "azure_openai_endpoint",
                    "message": "Required for selected provider.",
                    "type": "missing_provider_setting",
                },
                {
                    "field": "azure_openai_chat_deployment",
                    "message": "Required for selected provider.",
                    "type": "missing_provider_setting",
                },
                {
                    "field": "azure_openai_embedding_deployment",
                    "message": "Required for selected provider.",
                    "type": "missing_provider_setting",
                },
            ],
        },
    }


def test_setup_submit_endpoint_accepts_write_only_api_key_without_returning_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.post(
        "/setup",
        json={
            "email_provider": "gmail",
            "llm_provider": "ollama",
            "classification_mode": "local",
            "azure_openai_api_key": "super-secret-api-key",
        },
    )

    assert response.status_code == 200
    assert "super-secret-api-key" not in response.text


def test_setup_submit_endpoint_is_documented_in_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/setup"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    validation_schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"] == "#/components/schemas/SetupSubmitRequest"
    assert response_schema["$ref"] == "#/components/schemas/SetupSubmitResponse"
    assert validation_schema["$ref"] == "#/components/schemas/ApiErrorResponse"
