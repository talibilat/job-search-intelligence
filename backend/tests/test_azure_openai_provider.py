from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from app.config import AppSettings
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMProvider,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
    LLMTokenUsage,
)
from app.providers.llm.azure_openai import AzureOpenAIProvider, AzureOpenAITransportError
from app.security import SecretKind, SecretRef
from pydantic import SecretStr

AZURE_API_KEY_REF = SecretRef(
    kind=SecretKind.LLM_API_KEY,
    provider="azure_openai",
    name="api_key",
)


class FakeSecretStore:
    def __init__(self, secret: str | None) -> None:
        self._secret = SecretStr(secret) if secret is not None else None
        self.requested_refs: list[SecretRef] = []

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        self.requested_refs.append(ref)
        return self._secret

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        self._secret = value

    async def delete_secret(self, ref: SecretRef) -> None:
        self._secret = None


@dataclass(frozen=True)
class AzureTransportCall:
    url: str
    api_key: SecretStr
    payload: dict[str, object]
    timeout_seconds: int


@dataclass
class FakeAzureTransport:
    response: dict[str, object] | None = None
    error: AzureOpenAITransportError | None = None
    calls: list[AzureTransportCall] = field(default_factory=list)

    async def post_json(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.calls.append(
            AzureTransportCall(
                url=url,
                api_key=api_key,
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
        )
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        return {
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "message": {"content": '{"category":"rejection"}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }


def azure_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_version="2024-06-01",
        azure_openai_chat_deployment="jobtracker-chat",
        azure_openai_embedding_deployment="jobtracker-embedding",
        llm_timeout_seconds=17,
    )


def generation_request(
    *,
    model: str | None = None,
    response_format: LLMResponseFormat = LLMResponseFormat.TEXT,
) -> LLMGenerationRequest:
    return LLMGenerationRequest(
        messages=(
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content="Return only validated JSON.",
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content="Classify this synthetic job-search email.",
            ),
        ),
        model=model,
        response_format=response_format,
        options=LLMGenerationOptions(temperature=0, max_output_tokens=200),
    )


def test_azure_openai_provider_satisfies_llm_provider_protocol() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(),
    )

    assert isinstance(provider, LLMProvider)


def test_azure_openai_provider_posts_chat_completion_request() -> None:
    secret_store = FakeSecretStore("secret-api-key")
    transport = FakeAzureTransport()
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=secret_store,
        transport=transport,
    )

    response = asyncio.run(
        provider.generate(generation_request(response_format=LLMResponseFormat.JSON_OBJECT))
    )

    assert secret_store.requested_refs == [AZURE_API_KEY_REF]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.url == (
        "https://example.openai.azure.com/openai/deployments/"
        "jobtracker-chat/chat/completions?api-version=2024-06-01"
    )
    assert call.api_key.get_secret_value() == "secret-api-key"
    assert call.timeout_seconds == 17
    assert call.payload == {
        "messages": [
            {"role": "system", "content": "Return only validated JSON."},
            {
                "role": "user",
                "content": "Classify this synthetic job-search email.",
            },
        ],
        "temperature": 0.0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
    }
    assert "secret-api-key" not in str(call.payload)
    assert response.content == '{"category":"rejection"}'
    assert response.model == "gpt-4o-mini"
    assert response.finish_reason is LLMFinishReason.STOP
    assert response.usage == LLMTokenUsage(
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
    )


def test_azure_openai_provider_uses_request_model_as_deployment_override() -> None:
    transport = FakeAzureTransport(
        response={
            "choices": [
                {
                    "message": {"content": "truncated"},
                    "finish_reason": "length",
                }
            ]
        }
    )
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=transport,
    )

    response = asyncio.run(provider.generate(generation_request(model="alternate-chat")))

    assert transport.calls[0].url == (
        "https://example.openai.azure.com/openai/deployments/"
        "alternate-chat/chat/completions?api-version=2024-06-01"
    )
    assert response.model == "alternate-chat"
    assert response.finish_reason is LLMFinishReason.LENGTH


def test_azure_openai_provider_allows_empty_filtered_completion() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(
            response={
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {"content": ""},
                        "finish_reason": "content_filter",
                    }
                ],
            }
        ),
    )

    response = asyncio.run(provider.generate(generation_request()))

    assert response.content == ""
    assert response.finish_reason is LLMFinishReason.CONTENT_FILTER


def test_azure_openai_provider_requires_secret_store_api_key() -> None:
    transport = FakeAzureTransport()
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore(None),
        transport=transport,
    )

    with pytest.raises(LLMProviderUnavailableError) as error:
        asyncio.run(provider.generate(generation_request()))

    assert str(error.value) == "Azure OpenAI API key is not configured."
    assert transport.calls == []


def test_azure_openai_provider_rejects_malformed_response() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(response={"choices": []}),
    )

    with pytest.raises(LLMProviderResponseError) as error:
        asyncio.run(provider.generate(generation_request()))

    assert str(error.value) == "Azure OpenAI returned an invalid response."
    assert "secret-api-key" not in str(error.value)


def test_azure_openai_provider_maps_transient_transport_errors() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(error=AzureOpenAITransportError(status_code=429)),
    )

    with pytest.raises(LLMProviderUnavailableError) as error:
        asyncio.run(provider.generate(generation_request()))

    assert str(error.value) == "Azure OpenAI is temporarily unavailable."


def test_azure_openai_provider_maps_timeout_transport_errors() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(
            error=AzureOpenAITransportError(status_code=None, reason="timeout")
        ),
    )

    with pytest.raises(LLMProviderTimeoutError) as error:
        asyncio.run(provider.generate(generation_request()))

    assert str(error.value) == "Azure OpenAI request timed out."


def test_azure_openai_provider_maps_non_timeout_transport_errors() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(
            error=AzureOpenAITransportError(
                status_code=None,
                reason="[Errno 8] nodename nor servname provided",
            )
        ),
    )

    with pytest.raises(LLMProviderUnavailableError) as error:
        asyncio.run(provider.generate(generation_request()))

    assert str(error.value) == "Azure OpenAI is temporarily unavailable."
