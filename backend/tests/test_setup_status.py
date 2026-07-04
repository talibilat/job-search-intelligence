from __future__ import annotations

import pytest
from app.config import (
    AppSettings,
    ClassificationMode,
    LLMProviderName,
    get_settings,
)
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient


def clear_jobtracker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)


def create_test_app(settings: AppSettings) -> FastAPI:
    fastapi_app = create_app()

    def override_settings() -> AppSettings:
        return settings

    fastapi_app.dependency_overrides[get_settings] = override_settings
    return fastapi_app


def test_setup_status_endpoint_returns_phase_zero_shell_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    client = TestClient(create_test_app(AppSettings(_env_file=None)))

    response = client.get("/setup/status")

    assert response.status_code == 200
    assert response.json() == {
        "setup_complete": False,
        "gmail_connected": False,
        "llm_configured": False,
        "email_provider": "gmail",
        "llm_provider": "ollama",
        "classification_mode": "local",
    }


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
    assert response.json() == {
        "status": "accepted",
        "setup_complete": False,
        "gmail_connected": False,
        "llm_configured": False,
        "email_provider": "gmail",
        "llm_provider": "ollama",
        "classification_mode": "local",
    }


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


def test_setup_submit_endpoint_rejects_unknown_secret_like_fields(
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

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
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
