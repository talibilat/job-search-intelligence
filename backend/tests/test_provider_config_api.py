from __future__ import annotations

import pytest
from app.api.dependencies import (
    get_llm_secret_store,
    get_provider_configuration_repository,
)
from app.api.provider_config import get_active_sync_scheduler, get_provider_registry
from app.config import (
    AppSettings,
    ClassificationMode,
    EmailProviderName,
    LLMProviderName,
    get_settings,
)
from app.main import create_app
from app.providers import (
    EmailProviderRegistration,
    LLMProviderRegistration,
    ProviderConfigRequirement,
    ProviderRegistry,
    provider_registry,
)
from app.security import SecretRef
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr


class RecordingScheduler:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.jobs: list[dict[str, object]] = []
        self.settings = settings
        self.settings_at_add: list[tuple[bool, int]] = []

    def add_job(self, *args: object, **kwargs: object) -> None:
        self.jobs.append(dict(kwargs))
        if self.settings is not None:
            self.settings_at_add.append(
                (self.settings.sync_on_open, self.settings.sync_interval_seconds)
            )

    def remove_job(self, job_id: str) -> None:
        return None

    def start(self) -> None:
        return None

    def shutdown(self, *, wait: bool) -> None:
        return None


class FailingScheduler(RecordingScheduler):
    def add_job(self, *args: object, **kwargs: object) -> None:
        if kwargs.get("next_run_time") is None:
            raise RuntimeError("scheduler exploded")


class NoopConfigScheduler:
    def reconfigure(self, *, sync_on_open: bool, interval_seconds: int) -> None:
        return None


class MemoryProviderConfigRepository:
    def save(self, settings: AppSettings) -> None:
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


def clear_jobtracker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)


def create_test_app(
    settings: AppSettings,
    scheduler: RecordingScheduler | None = None,
) -> FastAPI:
    fastapi_app = create_app(settings=settings, scheduler=scheduler)
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    if scheduler is None:
        fastapi_app.dependency_overrides[get_active_sync_scheduler] = NoopConfigScheduler
    fastapi_app.dependency_overrides[get_provider_configuration_repository] = (
        MemoryProviderConfigRepository
    )
    fastapi_app.dependency_overrides[get_llm_secret_store] = MemorySecretStore
    return fastapi_app


def create_test_app_with_registry(
    settings: AppSettings,
    registry: ProviderRegistry,
) -> FastAPI:
    fastapi_app = create_test_app(settings)
    fastapi_app.dependency_overrides[get_provider_registry] = lambda: registry
    return fastapi_app


def custom_provider_registry() -> ProviderRegistry:
    gmail = provider_registry.get_email_provider(EmailProviderName.GMAIL)
    azure = provider_registry.get_llm_provider(LLMProviderName.AZURE_OPENAI)
    ollama = provider_registry.get_llm_provider(LLMProviderName.OLLAMA)
    return ProviderRegistry(
        email_providers=(
            EmailProviderRegistration(
                name=gmail.name,
                display_name="Injected Gmail",
                config_requirements=gmail.config_requirements,
                secret_requirements=gmail.secret_requirements,
            ),
        ),
        llm_providers=(
            LLMProviderRegistration(
                name=azure.name,
                display_name=azure.display_name,
                is_local=azure.is_local,
                config_requirements=azure.config_requirements,
                secret_requirements=azure.secret_requirements,
            ),
            LLMProviderRegistration(
                name=ollama.name,
                display_name=ollama.display_name,
                is_local=ollama.is_local,
                config_requirements=(
                    ProviderConfigRequirement(
                        setting_name="ollama_base_url",
                        label="Injected Ollama base URL",
                    ),
                ),
                secret_requirements=ollama.secret_requirements,
            ),
        ),
    )


def test_provider_config_endpoint_returns_current_selection_and_metadata_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.get("/config/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection"] == {
        "email_provider": "gmail",
        "llm_provider": "ollama",
        "classification_mode": "local",
    }
    assert payload["recommended_classification_mode"] == "local"
    assert payload["settings"]["ollama_chat_model"] == "llama3.1"
    assert payload["email_providers"][0]["name"] == "gmail"
    assert payload["email_providers"][0]["secret_requirements"] == [
        {
            "ref": {
                "kind": "oauth_client",
                "provider": "gmail",
                "name": "desktop_client_json",
            },
            "label": "Google Desktop OAuth client JSON",
            "required": True,
            "enforcement": "declarative",
        },
        {
            "ref": {
                "kind": "oauth_token",
                "provider": "gmail",
                "name": "refresh_token",
            },
            "label": "Gmail OAuth refresh token",
            "required": True,
            "enforcement": "declarative",
        },
    ]
    assert {provider["name"] for provider in payload["llm_providers"]} == {
        "azure_openai",
        "ollama",
    }
    assert "api_key" in response.text
    assert "super-secret" not in response.text


def test_provider_config_endpoint_uses_injected_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(
        create_test_app_with_registry(
            AppSettings(_env_file=None),
            custom_provider_registry(),
        ),
    )

    response = client.get("/config/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_providers"][0]["display_name"] == "Injected Gmail"
    assert payload["llm_providers"][1]["config_requirements"] == [
        {
            "setting_name": "ollama_base_url",
            "label": "Injected Ollama base URL",
            "required": True,
            "enforcement": "selection",
        },
    ]


def test_provider_config_update_validates_and_updates_in_process_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    settings = AppSettings(_env_file=None)
    client = TestClient(create_test_app(settings))

    response = client.put(
        "/config/providers",
        json={
            "llm_provider": "azure_openai",
            "classification_mode": "hybrid",
            "azure_openai_endpoint": "https://example.openai.azure.com",
            "azure_openai_chat_deployment": "chat",
            "azure_openai_embedding_deployment": "embeddings",
        },
    )

    assert response.status_code == 200
    assert response.json()["selection"] == {
        "email_provider": "gmail",
        "llm_provider": "azure_openai",
        "classification_mode": "hybrid",
    }
    assert response.json()["recommended_classification_mode"] == "hybrid"
    assert response.json()["settings"]["azure_openai_endpoint"] == (
        "https://example.openai.azure.com"
    )

    follow_up = client.get("/config/providers")

    assert follow_up.status_code == 200
    assert follow_up.json()["selection"]["llm_provider"] == "azure_openai"
    assert follow_up.json()["settings"]["azure_openai_chat_deployment"] == "chat"


def test_provider_config_update_reconfigures_active_scheduler_before_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        sync_on_open=False,
        sync_interval_seconds=3600,
    )
    scheduler = RecordingScheduler(settings)
    app = create_test_app(settings, scheduler)

    with TestClient(app) as client:
        response = client.put(
            "/config/providers",
            json={"sync_on_open": True, "sync_interval_seconds": 1800},
        )

    assert response.status_code == 200
    assert scheduler.jobs == [
        {
            "seconds": 1800,
            "id": "gmail-sync-on-open",
            "replace_existing": True,
        }
    ]
    assert scheduler.settings_at_add == [(False, 3600)]
    assert settings.sync_on_open is True
    assert settings.sync_interval_seconds == 1800


def test_provider_config_update_does_not_mutate_settings_when_scheduler_fails() -> None:
    settings = AppSettings(
        _env_file=None,
        sync_on_open=False,
        sync_interval_seconds=3600,
    )
    app = create_test_app(settings, FailingScheduler())

    with TestClient(app) as client:
        response = client.put(
            "/config/providers",
            json={"sync_on_open": True, "sync_interval_seconds": 1800},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Sync scheduler settings could not be applied.",
            "details": [],
        }
    }
    assert settings.sync_on_open is False
    assert settings.sync_interval_seconds == 3600
    assert "scheduler exploded" not in response.text


def test_provider_config_update_returns_typed_error_for_invalid_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.put(
        "/config/providers",
        json={
            "llm_provider": "azure_openai",
            "classification_mode": "local",
            "azure_openai_endpoint": "https://example.openai.azure.com",
            "azure_openai_chat_deployment": "chat",
            "azure_openai_embedding_deployment": "embeddings",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Azure OpenAI cannot be used with local classification mode.",
            "details": [],
        },
    }


def test_provider_config_update_preselects_hybrid_when_switching_to_azure_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    settings = AppSettings(_env_file=None)
    client = TestClient(create_test_app(settings))

    response = client.put(
        "/config/providers",
        json={
            "llm_provider": "azure_openai",
            "azure_openai_endpoint": "https://example.openai.azure.com",
            "azure_openai_chat_deployment": "chat",
            "azure_openai_embedding_deployment": "embeddings",
        },
    )

    assert response.status_code == 200
    assert response.json()["selection"]["classification_mode"] == "hybrid"
    assert response.json()["recommended_classification_mode"] == "hybrid"


def test_provider_config_update_preserves_classification_mode_for_same_provider(
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

    response = client.put(
        "/config/providers",
        json={
            "llm_provider": "azure_openai",
            "azure_openai_chat_deployment": "updated-chat",
        },
    )

    assert response.status_code == 200
    assert response.json()["selection"] == {
        "email_provider": "gmail",
        "llm_provider": "azure_openai",
        "classification_mode": "llm",
    }
    assert settings.classification_mode is ClassificationMode.LLM
    assert settings.azure_openai_chat_deployment == "updated-chat"


def test_provider_config_update_reports_missing_provider_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.put(
        "/config/providers",
        json={
            "llm_provider": "azure_openai",
            "classification_mode": "hybrid",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Selected LLM provider is missing required non-secret settings.",
            "details": [
                {
                    "field": "azure_openai_endpoint",
                    "message": "Required provider setting is missing.",
                    "type": "missing",
                },
                {
                    "field": "azure_openai_chat_deployment",
                    "message": "Required provider setting is missing.",
                    "type": "missing",
                },
            ],
        },
    }


def test_provider_config_update_accepts_write_only_api_key_without_returning_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.put(
        "/config/providers",
        json={
            "llm_provider": "ollama",
            "classification_mode": "local",
            "azure_openai_api_key": "super-secret-api-key",
        },
    )

    assert response.status_code == 200
    assert "super-secret-api-key" not in response.text


def test_provider_config_update_returns_typed_error_for_settings_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.put(
        "/config/providers",
        json={"gmail_scopes": ["https://mail.google.com/"]},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "field": "body.gmail_scopes",
                    "message": "Extra inputs are not permitted",
                    "type": "extra_forbidden",
                },
            ],
        },
    }


def test_provider_config_endpoint_is_documented_in_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert paths["/config/providers"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ProviderConfigResponse"}
    assert paths["/config/providers"]["put"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ProviderConfigResponse"}
    assert paths["/config/providers"]["put"]["responses"]["503"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ApiErrorResponse"}
