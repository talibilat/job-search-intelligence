from __future__ import annotations

import pytest
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient


def clear_jobtracker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)


def create_test_app(settings: AppSettings) -> FastAPI:
    fastapi_app = create_app()
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    return fastapi_app


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
