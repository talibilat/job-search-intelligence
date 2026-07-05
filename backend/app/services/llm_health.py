from __future__ import annotations

from app.config import AppSettings, LLMProviderName
from app.providers import ProviderRegistry, provider_registry
from app.providers.llm import (
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProvider,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)


def configured_llm_health_check_request(
    settings: AppSettings,
) -> LLMProviderHealthCheckRequest:
    """Build the health-check request from the selected non-secret settings."""

    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return LLMProviderHealthCheckRequest(
            chat_model=settings.azure_openai_chat_deployment,
            embedding_model=settings.azure_openai_embedding_deployment,
        )
    return LLMProviderHealthCheckRequest(
        chat_model=settings.ollama_chat_model,
        embedding_model=settings.ollama_embedding_model,
    )


async def check_configured_llm_provider_health(
    settings: AppSettings,
    provider: LLMProvider,
    registry: ProviderRegistry = provider_registry,
) -> LLMProviderHealthCheckResponse:
    """Verify the selected LLM provider checked every configured model."""

    registry.validate_settings(settings)
    request = configured_llm_health_check_request(settings)
    response = await provider.health_check(request)
    _validate_health_response(settings, request, response)
    return response


async def ensure_configured_llm_provider_available(
    settings: AppSettings,
    provider: LLMProvider,
    registry: ProviderRegistry = provider_registry,
) -> LLMProviderHealthCheckResponse:
    """Fail before a run when configured LLM models are unavailable."""

    response = await check_configured_llm_provider_health(settings, provider, registry)
    if response.status is LLMModelHealthStatus.UNAVAILABLE:
        raise LLMProviderUnavailableError(
            public_message="Configured LLM provider models are unavailable."
        )
    return response


def _validate_health_response(
    settings: AppSettings,
    request: LLMProviderHealthCheckRequest,
    response: LLMProviderHealthCheckResponse,
) -> None:
    if response.provider_name != settings.llm_provider.value:
        raise LLMProviderResponseError(
            public_message="LLM provider health check returned the wrong provider."
        )

    expected_checks = {
        (LLMModelKind.CHAT, request.chat_model),
        (LLMModelKind.EMBEDDING, request.embedding_model),
    }
    actual_checks = {(check.kind, check.model) for check in response.checks}
    if len(response.checks) != len(expected_checks) or actual_checks != expected_checks:
        raise LLMProviderResponseError(
            public_message="LLM provider health check did not verify the configured models."
        )
