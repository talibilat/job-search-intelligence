from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from app.api.dependencies import get_llm_provider
from app.config import AppSettings, ClassificationMode, LLMProviderName
from app.providers.llm import (
    LLMEmbedding,
    LLMEmbeddingProvider,
    LLMEmbeddingRequest,
    LLMFinishReason,
    LLMGenerationChunk,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProvider,
    LLMProviderHealthCheckRequest,
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
EMBEDDING_1536 = tuple(0.002 for _ in range(1536))


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
    stream_events: tuple[dict[str, object] | None, ...] = (
        {
            "model": "gpt-4o-mini",
            "choices": [{"delta": {"content": "Grounded "}, "finish_reason": None}],
        },
        {
            "model": "gpt-4o-mini",
            "choices": [{"delta": {"content": "answer"}, "finish_reason": None}],
        },
        {
            "model": "gpt-4o-mini",
            "choices": [{"delta": {}, "finish_reason": "stop"}],
        },
        {
            "model": "gpt-4o-mini",
            "choices": [],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        },
        None,
    )

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
        if "/embeddings?" in url:
            return {
                "model": "jobtracker-embedding",
                "data": [{"index": 0, "embedding": list(EMBEDDING_1536)}],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            }
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

    async def stream_sse(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> AsyncIterator[dict[str, object] | None]:
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
        for event in self.stream_events:
            yield event


def azure_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_version="2024-06-01",
        azure_openai_chat_deployment="jobtracker-chat",
        azure_openai_embedding_deployment="jobtracker-embedding",
        llm_timeout_seconds=17,
    )


def test_llm_provider_dependency_resolves_selected_azure_provider() -> None:
    provider = get_llm_provider(azure_settings(), FakeSecretStore("api-key"))

    assert isinstance(provider, AzureOpenAIProvider)
    assert provider.provider_name == "azure_openai"
    assert "api-key" not in repr(provider)


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
    assert isinstance(provider, LLMEmbeddingProvider)


def test_azure_openai_health_check_verifies_chat_deployment() -> None:
    transport = FakeAzureTransport()
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=transport,
    )

    response = asyncio.run(
        provider.health_check(
            LLMProviderHealthCheckRequest(
                chat_model="jobtracker-chat",
                embedding_model="jobtracker-embedding",
            )
        )
    )

    assert len(transport.calls) == 2
    assert transport.calls[0].url == (
        "https://example.openai.azure.com/openai/deployments/"
        "jobtracker-chat/chat/completions?api-version=2024-06-01"
    )
    assert transport.calls[1].url == (
        "https://example.openai.azure.com/openai/deployments/"
        "jobtracker-embedding/embeddings?api-version=2024-06-01"
    )
    assert response.provider_name == "azure_openai"
    assert response.status is LLMModelHealthStatus.AVAILABLE
    assert response.checks == (
        LLMModelHealthCheck(
            kind=LLMModelKind.CHAT,
            model="jobtracker-chat",
            status=LLMModelHealthStatus.AVAILABLE,
        ),
        LLMModelHealthCheck(
            kind=LLMModelKind.EMBEDDING,
            model="jobtracker-embedding",
            status=LLMModelHealthStatus.AVAILABLE,
        ),
    )


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


def test_azure_openai_provider_streams_deltas_and_final_metadata() -> None:
    async def collect(provider: AzureOpenAIProvider) -> list[LLMGenerationChunk]:
        return [
            chunk
            async for chunk in provider.stream_generate(
                generation_request(response_format=LLMResponseFormat.JSON_OBJECT)
            )
        ]

    transport = FakeAzureTransport()
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=transport,
    )

    chunks = asyncio.run(collect(provider))

    assert [chunk.content_delta for chunk in chunks] == ["Grounded ", "answer", ""]
    assert all(chunk.model == "gpt-4o-mini" for chunk in chunks)
    assert chunks[-1].finish_reason is LLMFinishReason.STOP
    assert chunks[-1].usage == LLMTokenUsage(
        prompt_tokens=4,
        completion_tokens=2,
        total_tokens=6,
    )
    assert transport.calls[0].payload["stream"] is True
    assert transport.calls[0].payload["stream_options"] == {"include_usage": True}
    assert transport.calls[0].payload["response_format"] == {"type": "json_object"}


def test_azure_openai_provider_stream_allows_content_filter_terminal_chunk() -> None:
    transport = FakeAzureTransport(
        stream_events=(
            {
                "model": "gpt-4o-mini",
                "choices": [{"delta": {}, "finish_reason": "content_filter"}],
            },
            None,
        )
    )
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=transport,
    )

    async def collect() -> list[LLMGenerationChunk]:
        return [chunk async for chunk in provider.stream_generate(generation_request())]

    chunks = asyncio.run(collect())

    assert chunks == [
        LLMGenerationChunk(
            content_delta="",
            model="gpt-4o-mini",
            finish_reason=LLMFinishReason.CONTENT_FILTER,
        )
    ]


def test_azure_openai_provider_rejects_incomplete_stream() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(stream_events=()),
    )

    async def collect() -> list[LLMGenerationChunk]:
        return [chunk async for chunk in provider.stream_generate(generation_request())]

    with pytest.raises(LLMProviderResponseError):
        asyncio.run(collect())


def test_azure_openai_provider_maps_stream_timeout() -> None:
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=FakeSecretStore("secret-api-key"),
        transport=FakeAzureTransport(
            error=AzureOpenAITransportError(status_code=None, reason="timeout")
        ),
    )

    async def collect() -> list[LLMGenerationChunk]:
        return [chunk async for chunk in provider.stream_generate(generation_request())]

    with pytest.raises(LLMProviderTimeoutError):
        asyncio.run(collect())


def test_azure_openai_provider_posts_embedding_request() -> None:
    secret_store = FakeSecretStore("secret-api-key")
    transport = FakeAzureTransport(
        response={
            "model": "jobtracker-embedding",
            "data": [
                {"index": 0, "embedding": list(EMBEDDING_1536)},
                {"index": 1, "embedding": list(EMBEDDING_1536)},
            ],
            "usage": {"prompt_tokens": 9, "total_tokens": 9},
        }
    )
    provider = AzureOpenAIProvider(
        settings=azure_settings(),
        secret_store=secret_store,
        transport=transport,
    )

    response = asyncio.run(
        provider.embed(
            LLMEmbeddingRequest(
                inputs=("first retained chunk", "second retained chunk"),
            )
        )
    )

    assert secret_store.requested_refs == [AZURE_API_KEY_REF]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.url == (
        "https://example.openai.azure.com/openai/deployments/"
        "jobtracker-embedding/embeddings?api-version=2024-06-01"
    )
    assert call.payload == {"input": ["first retained chunk", "second retained chunk"]}
    assert response.model == "jobtracker-embedding"
    assert response.embeddings == (
        LLMEmbedding(index=0, embedding=EMBEDDING_1536),
        LLMEmbedding(index=1, embedding=EMBEDDING_1536),
    )
    assert response.usage == LLMTokenUsage(prompt_tokens=9, total_tokens=9)


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
