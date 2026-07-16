from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import AppSettings, ClassificationMode, EmailProviderName, LLMProviderName
from app.db.repositories import ProviderConfigurationRepository
from app.models.provider_config import ProviderConfigUpdateRequest, ReadinessState
from app.providers import provider_registry
from app.providers.email import EmailAccountRef, EmailConnection
from app.providers.llm import (
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
)
from app.security import (
    AZURE_OPENAI_API_KEY_REF,
    GMAIL_OAUTH_CLIENT_REF,
    SecretKind,
    SecretRef,
)
from app.services.provider_config import (
    apply_provider_config_update,
    import_azure_openai_api_key_from_environment,
)
from app.services.readiness import ProviderReadinessService
from pydantic import SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CLIENT_JSON = """{"installed":{"client_id":"client","client_secret":"secret","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}}"""


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[SecretRef, SecretStr] = {}

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return self.values.get(ref)

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        self.values[ref] = value

    async def delete_secret(self, ref: SecretRef) -> None:
        self.values.pop(ref, None)


class NoopScheduler:
    def reconfigure(self, *, sync_on_open: bool, interval_seconds: int) -> None:
        return None


def test_environment_azure_key_replaces_a_stale_saved_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_store = MemorySecretStore()
    secret_store.values[AZURE_OPENAI_API_KEY_REF] = SecretStr("stale-key")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "current-key")

    asyncio.run(import_azure_openai_api_key_from_environment(secret_store))

    assert secret_store.values[AZURE_OPENAI_API_KEY_REF].get_secret_value() == "current-key"


class HealthyProvider:
    async def health_check(
        self, request: LLMProviderHealthCheckRequest
    ) -> LLMProviderHealthCheckResponse:
        return LLMProviderHealthCheckResponse(
            provider_name="azure_openai",
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


class UnavailableProvider(HealthyProvider):
    async def health_check(
        self, request: LLMProviderHealthCheckRequest
    ) -> LLMProviderHealthCheckResponse:
        response = await super().health_check(request)
        checks = tuple(
            check.model_copy(update={"status": LLMModelHealthStatus.UNAVAILABLE})
            for check in response.checks
        )
        return LLMProviderHealthCheckResponse(
            provider_name=response.provider_name,
            status=LLMModelHealthStatus.UNAVAILABLE,
            checks=checks,
        )


class Connections:
    def __init__(self, values: list[EmailConnection] | None = None) -> None:
        self.values = values or []

    def list_connections_metadata(self) -> list[EmailConnection]:
        return self.values


def migrate(database_path: Path) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")


def test_provider_settings_and_credentials_persist_without_secret_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate(database_path)
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    secret_store = MemorySecretStore()
    with sqlite3.connect(database_path) as connection:
        response = asyncio.run(
            apply_provider_config_update(
                settings,
                ProviderConfigUpdateRequest(
                    llm_provider=LLMProviderName.AZURE_OPENAI,
                    azure_openai_endpoint="https://example.openai.azure.com",
                    azure_openai_chat_deployment="chat",
                    azure_openai_embedding_deployment="embedding",
                    azure_openai_api_key=SecretStr("top-secret-key"),
                    gmail_oauth_client_json=SecretStr(CLIENT_JSON),
                ),
                provider_registry,
                repository=ProviderConfigurationRepository(connection),
                secret_store=secret_store,
                sync_scheduler=NoopScheduler(),  # type: ignore[arg-type]
            )
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(provider_configuration)")
        }

    restarted = AppSettings(_env_file=None, database_url=settings.database_url)
    with sqlite3.connect(database_path) as connection:
        record = ProviderConfigurationRepository(connection).fetch()
    assert record is not None
    from app.services.provider_config import apply_persisted_provider_config

    apply_persisted_provider_config(restarted, record)

    assert restarted.llm_provider is LLMProviderName.AZURE_OPENAI
    assert restarted.azure_openai_chat_deployment == "chat"
    assert response.model_dump_json().find("top-secret-key") == -1
    assert "azure_openai_api_key" not in columns
    assert "gmail_oauth_client_json" not in columns
    assert secret_store.values[AZURE_OPENAI_API_KEY_REF].get_secret_value() == "top-secret-key"
    assert secret_store.values[GMAIL_OAUTH_CLIENT_REF].get_secret_value() == CLIENT_JSON


def test_readiness_propagates_missing_chat_credentials() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
    )
    result = asyncio.run(
        ProviderReadinessService(
            settings=settings,
            registry=provider_registry,
            connection_reader=Connections(),
            secret_store=MemorySecretStore(),
            llm_provider=HealthyProvider(),  # type: ignore[arg-type]
        ).check()
    )

    assert result.gmail_sync.state is ReadinessState.MISSING_CREDENTIAL
    assert result.classification_generation.state is ReadinessState.MISSING_CREDENTIAL
    assert result.embedding_generation.state is ReadinessState.MISSING_CREDENTIAL
    assert result.chat_generation.state is ReadinessState.MISSING_CREDENTIAL
    assert result.ready_to_sync is False
    assert result.ready_to_classify is False


def test_readiness_reports_ready_unavailable_reauth_and_missing_config() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
    )
    credential_ref = SecretRef(
        kind=SecretKind.OAUTH_TOKEN,
        provider="gmail",
        name="account",
    )
    connection = EmailConnection(
        account=EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com"),
        credential_ref=credential_ref,
        granted_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        connected_at=datetime(2026, 7, 14, tzinfo=UTC),
    )
    secrets = MemorySecretStore()
    secrets.values[GMAIL_OAUTH_CLIENT_REF] = SecretStr(CLIENT_JSON)
    secrets.values[AZURE_OPENAI_API_KEY_REF] = SecretStr("key")
    secrets.values[credential_ref] = SecretStr("token")

    ready = asyncio.run(
        ProviderReadinessService(
            settings=settings,
            registry=provider_registry,
            connection_reader=Connections([connection]),
            secret_store=secrets,
            llm_provider=HealthyProvider(),  # type: ignore[arg-type]
        ).check()
    )
    unavailable = asyncio.run(
        ProviderReadinessService(
            settings=settings,
            registry=provider_registry,
            connection_reader=Connections([connection]),
            secret_store=secrets,
            llm_provider=UnavailableProvider(),  # type: ignore[arg-type]
        ).check()
    )
    reauth = asyncio.run(
        ProviderReadinessService(
            settings=settings,
            registry=provider_registry,
            connection_reader=Connections(
                [connection.model_copy(update={"reauth_required": True})]
            ),
            secret_store=secrets,
            llm_provider=HealthyProvider(),  # type: ignore[arg-type]
        ).check()
    )
    missing_config = asyncio.run(
        ProviderReadinessService(
            settings=settings.model_copy(update={"azure_openai_endpoint": ""}),
            registry=provider_registry,
            connection_reader=Connections([connection]),
            secret_store=secrets,
            llm_provider=HealthyProvider(),  # type: ignore[arg-type]
        ).check()
    )

    assert ready.ready_to_sync is True
    assert ready.ready_to_classify is True
    assert ready.embedding_generation.state is ReadinessState.READY
    assert ready.chat_generation.state is ReadinessState.READY
    assert unavailable.classification_generation.state is ReadinessState.UNAVAILABLE
    assert unavailable.chat_generation.state is ReadinessState.UNAVAILABLE
    assert reauth.gmail_sync.state is ReadinessState.REAUTH_REQUIRED
    assert missing_config.classification_generation.state is ReadinessState.MISSING_CONFIG
