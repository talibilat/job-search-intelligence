from __future__ import annotations

import asyncio

import pytest
from app.api.provider_config import get_configured_llm_provider
from app.config import AppSettings, ClassificationMode, LLMProviderName, get_settings
from app.main import create_app
from app.providers.llm import (
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from app.services.llm_health import ensure_configured_llm_provider_available
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError


class FakeLLMHealthProvider:
    provider_name = "ollama"

    def __init__(self, response: LLMProviderHealthCheckResponse | None = None) -> None:
        self.requests: list[LLMProviderHealthCheckRequest] = []
        self.response = response

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        return LLMGenerationResponse(
            content=request.messages[-1].content,
            model=request.model or "fake-model",
            finish_reason=LLMFinishReason.STOP,
        )

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        raise NotImplementedError

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        self.requests.append(request)
        if self.response is not None:
            return self.response
        return available_health_response(self.provider_name, request)


class TimeoutLLMHealthProvider:
    provider_name = "ollama"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        return LLMGenerationResponse(
            content=request.messages[-1].content,
            model=request.model or "fake-model",
            finish_reason=LLMFinishReason.STOP,
        )

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        raise NotImplementedError

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        del request
        raise LLMProviderTimeoutError(public_message="LLM provider health check timed out.")


def available_health_response(
    provider_name: str,
    request: LLMProviderHealthCheckRequest,
) -> LLMProviderHealthCheckResponse:
    return LLMProviderHealthCheckResponse(
        provider_name=provider_name,
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


def create_health_test_app(
    *,
    settings: AppSettings,
    provider: object,
) -> FastAPI:
    fastapi_app = create_app()
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    fastapi_app.dependency_overrides[get_configured_llm_provider] = lambda: provider
    return fastapi_app


def test_llm_provider_health_endpoint_checks_configured_ollama_models() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.OLLAMA,
        classification_mode=ClassificationMode.LOCAL,
        ollama_chat_model="llama3.2",
        ollama_embedding_model="nomic-embed-text",
    )
    provider = FakeLLMHealthProvider()
    client = TestClient(create_health_test_app(settings=settings, provider=provider))

    response = client.post("/config/providers/llm/health")

    assert response.status_code == 200
    assert response.json() == {
        "provider_name": "ollama",
        "status": "available",
        "checks": [
            {
                "kind": "chat",
                "model": "llama3.2",
                "status": "available",
                "detail": None,
            },
            {
                "kind": "embedding",
                "model": "nomic-embed-text",
                "status": "available",
                "detail": None,
            },
        ],
    }
    assert provider.requests == [
        LLMProviderHealthCheckRequest(
            chat_model="llama3.2",
            embedding_model="nomic-embed-text",
        )
    ]


def test_llm_provider_health_endpoint_checks_configured_azure_deployments() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="jt-chat",
        azure_openai_embedding_deployment="jt-embeddings",
    )
    provider = FakeLLMHealthProvider(
        LLMProviderHealthCheckResponse(
            provider_name="azure_openai",
            status=LLMModelHealthStatus.AVAILABLE,
            checks=(
                LLMModelHealthCheck(
                    kind=LLMModelKind.CHAT,
                    model="jt-chat",
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
                LLMModelHealthCheck(
                    kind=LLMModelKind.EMBEDDING,
                    model="jt-embeddings",
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
            ),
        )
    )
    client = TestClient(create_health_test_app(settings=settings, provider=provider))

    response = client.post("/config/providers/llm/health")

    assert response.status_code == 200
    assert provider.requests == [
        LLMProviderHealthCheckRequest(
            chat_model="jt-chat",
            embedding_model="jt-embeddings",
        )
    ]


def test_llm_provider_health_endpoint_rejects_missing_selected_provider_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="",
        azure_openai_chat_deployment="",
        azure_openai_embedding_deployment="",
    )
    provider = FakeLLMHealthProvider()
    client = TestClient(create_health_test_app(settings=settings, provider=provider))

    response = client.post("/config/providers/llm/health")

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
        }
    }
    assert provider.requests == []


def test_llm_health_endpoint_validates_settings_before_adapter_resolution() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="",
        azure_openai_chat_deployment="",
        azure_openai_embedding_deployment="",
    )
    fastapi_app = create_app()
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(fastapi_app)

    response = client.post("/config/providers/llm/health")

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
        }
    }


def test_llm_provider_health_endpoint_maps_provider_errors_to_public_response() -> None:
    settings = AppSettings(_env_file=None)
    client = TestClient(
        create_health_test_app(settings=settings, provider=TimeoutLLMHealthProvider())
    )

    response = client.post("/config/providers/llm/health")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "llm_provider_timeout",
            "message": "LLM provider health check timed out.",
            "details": [],
        }
    }


def test_health_check_response_rejects_available_status_with_unavailable_model() -> None:
    with pytest.raises(ValidationError):
        LLMProviderHealthCheckResponse(
            provider_name="ollama",
            status=LLMModelHealthStatus.AVAILABLE,
            checks=(
                LLMModelHealthCheck(
                    kind=LLMModelKind.CHAT,
                    model="llama3.2",
                    status=LLMModelHealthStatus.UNAVAILABLE,
                    detail="model is not pulled",
                ),
            ),
        )


def test_ensure_configured_llm_provider_available_blocks_unavailable_models() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.OLLAMA,
        classification_mode=ClassificationMode.LOCAL,
        ollama_chat_model="missing-chat",
        ollama_embedding_model="nomic-embed-text",
    )
    provider = FakeLLMHealthProvider(
        LLMProviderHealthCheckResponse(
            provider_name="ollama",
            status=LLMModelHealthStatus.UNAVAILABLE,
            checks=(
                LLMModelHealthCheck(
                    kind=LLMModelKind.CHAT,
                    model="missing-chat",
                    status=LLMModelHealthStatus.UNAVAILABLE,
                    detail="model is not pulled",
                ),
                LLMModelHealthCheck(
                    kind=LLMModelKind.EMBEDDING,
                    model="nomic-embed-text",
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
            ),
        )
    )

    with pytest.raises(LLMProviderUnavailableError) as error:
        asyncio.run(ensure_configured_llm_provider_available(settings, provider))

    assert error.value.public_message == "Configured LLM provider models are unavailable."


def test_health_service_rejects_responses_that_skip_configured_models() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.OLLAMA,
        classification_mode=ClassificationMode.LOCAL,
        ollama_chat_model="llama3.2",
        ollama_embedding_model="nomic-embed-text",
    )
    provider = FakeLLMHealthProvider(
        LLMProviderHealthCheckResponse(
            provider_name="ollama",
            status=LLMModelHealthStatus.AVAILABLE,
            checks=(
                LLMModelHealthCheck(
                    kind=LLMModelKind.CHAT,
                    model="llama3.2",
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
                LLMModelHealthCheck(
                    kind=LLMModelKind.EMBEDDING,
                    model="other-embedding",
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
            ),
        )
    )

    with pytest.raises(LLMProviderResponseError) as error:
        asyncio.run(ensure_configured_llm_provider_available(settings, provider))

    assert error.value.public_message == (
        "LLM provider health check did not verify the configured models."
    )


def test_llm_provider_health_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/config/providers/llm/health"]["post"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/LLMProviderHealthCheckResponse"


def test_llm_health_boundary_models_do_not_define_credential_fields() -> None:
    credential_field_names = {
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
        "credential",
        "credentials",
        "oauth_token",
    }
    boundary_models: tuple[type[BaseModel], ...] = (
        LLMModelHealthCheck,
        LLMProviderHealthCheckRequest,
        LLMProviderHealthCheckResponse,
    )

    for model in boundary_models:
        assert credential_field_names.isdisjoint(model.model_fields)
