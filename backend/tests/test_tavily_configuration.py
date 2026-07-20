from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, WebSearchProviderName
from app.db.repositories import ProviderConfigurationRepository
from app.models.provider_config import ProviderConfigUpdateRequest, ReadinessState
from app.providers import provider_registry
from app.providers.llm import (
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
)
from app.security import TAVILY_API_KEY_REF, SecretRef
from app.services.provider_config import apply_provider_config_update
from app.services.readiness import ProviderReadinessService
from pydantic import SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]


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
        del sync_on_open, interval_seconds


class NoConnections:
    def list_connections_metadata(self) -> list[object]:
        return []


class HealthyLocalProvider:
    async def health_check(
        self, request: LLMProviderHealthCheckRequest
    ) -> LLMProviderHealthCheckResponse:
        checks = (
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
        )
        return LLMProviderHealthCheckResponse(
            provider_name="ollama",
            status=LLMModelHealthStatus.AVAILABLE,
            checks=checks,
        )


def migrate(database_path: Path, revision: str = "head") -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, revision)


def test_tavily_configuration_persists_without_secret_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate(database_path)
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    secrets = MemorySecretStore()
    with sqlite3.connect(database_path) as connection:
        response = asyncio.run(
            apply_provider_config_update(
                settings,
                ProviderConfigUpdateRequest(
                    web_search_enabled=True,
                    web_search_provider=WebSearchProviderName.TAVILY,
                    tavily_base_url="https://search.example.com",
                    web_search_max_results=8,
                    web_search_timeout_seconds=12,
                    tavily_api_key=SecretStr("write-only-key"),
                ),
                provider_registry,
                repository=ProviderConfigurationRepository(connection),
                secret_store=secrets,
                sync_scheduler=NoopScheduler(),  # type: ignore[arg-type]
            )
        )
        record = ProviderConfigurationRepository(connection).fetch()
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(provider_configuration)")
        }

    assert record is not None
    assert record.web_search_enabled is True
    assert record.web_search_provider is WebSearchProviderName.TAVILY
    assert record.web_search_max_results == 8
    assert "tavily_api_key" not in columns
    assert "write-only-key" not in response.model_dump_json()
    assert secrets.values[TAVILY_API_KEY_REF].get_secret_value() == "write-only-key"


def test_0247_preserves_existing_singleton_and_adds_nonsecret_defaults(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate(database_path, "20260718_0246")
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO provider_configuration (
                singleton_id, email_provider, llm_provider, classification_mode,
                sync_on_open, sync_interval_seconds, azure_openai_endpoint,
                azure_openai_api_version, azure_openai_chat_deployment,
                azure_openai_embedding_deployment, ollama_base_url,
                ollama_chat_model, ollama_embedding_model, updated_at
            ) VALUES (1, 'gmail', 'ollama', 'local', 1, 900, '', '2024-06-01', '', '',
                      'http://127.0.0.1:11434', 'llama3.1', 'nomic-embed-text',
                      '2026-07-18T00:00:00+00:00')
            """
        )
        connection.commit()
        legacy_record = ProviderConfigurationRepository(connection).fetch()
    assert legacy_record is not None
    assert legacy_record.web_search_enabled is False
    assert legacy_record.web_search_provider is WebSearchProviderName.TAVILY
    migrate(database_path)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT singleton_id, web_search_enabled, web_search_provider,
                   tavily_base_url, web_search_max_results, web_search_timeout_seconds
            FROM provider_configuration
            """
        ).fetchone()

    assert row == (1, 0, "tavily", "https://api.tavily.com", 5, 10)
    assert settings.web_search_enabled is False


def test_web_search_readiness_is_separate_from_local_chat_readiness() -> None:
    settings = AppSettings(_env_file=None, web_search_enabled=True)
    secrets = MemorySecretStore()
    service = ProviderReadinessService(
        settings=settings,
        registry=provider_registry,
        connection_reader=NoConnections(),  # type: ignore[arg-type]
        secret_store=secrets,
        llm_provider=HealthyLocalProvider(),  # type: ignore[arg-type]
    )

    missing = asyncio.run(service.check())
    secrets.values[TAVILY_API_KEY_REF] = SecretStr("key")
    ready = asyncio.run(service.check())

    assert missing.chat_generation.state is ReadinessState.READY
    assert missing.web_search.state is ReadinessState.MISSING_CREDENTIAL
    assert ready.chat_generation.state is ReadinessState.READY
    assert ready.web_search.state is ReadinessState.READY
