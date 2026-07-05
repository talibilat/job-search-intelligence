from __future__ import annotations

import pytest
from app.api.provider_config import get_provider_registry
from app.config import AppSettings, EmailProviderName, LLMProviderName, get_settings
from app.main import create_app
from app.providers import (
    EmailProviderRegistration,
    LLMProviderRegistration,
    ProviderConfigRequirement,
    ProviderRegistry,
    provider_registry,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def clear_jobtracker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)


def create_test_app(settings: AppSettings) -> FastAPI:
    fastapi_app = create_app()
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
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
                {
                    "field": "azure_openai_embedding_deployment",
                    "message": "Required provider setting is missing.",
                    "type": "missing",
                },
            ],
        },
    }


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
            "message": "Provider config validation failed.",
            "details": [
                {
                    "field": "gmail_scopes",
                    "message": "Value error, gmail_scopes must only include gmail.readonly in v1",
                    "type": "value_error",
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
