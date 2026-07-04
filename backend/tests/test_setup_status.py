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
