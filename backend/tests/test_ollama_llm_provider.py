from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest
from app.config import AppSettings
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
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProvider,
    LLMProviderHealthCheckRequest,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
    LLMTokenUsage,
)
from app.providers.llm.ollama import (
    OllamaChatResponse,
    OllamaChatStreamResponse,
    OllamaChatTransportRequest,
    OllamaEmbeddingResponse,
    OllamaEmbeddingTransportRequest,
    OllamaLLMProvider,
    OllamaTransportError,
    OllamaTransportInvalidResponseError,
    OllamaTransportTimeoutError,
    UrllibOllamaTransport,
)
from app.security import SecretRef
from pydantic import SecretStr

EMBEDDING_1536 = tuple(0.003 for _ in range(1536))


class FakeSecretStore:
    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        del ref
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        del ref


class FakeOllamaTransport:
    def __init__(
        self,
        *,
        response: OllamaChatResponse | None = None,
        embedding_response: OllamaEmbeddingResponse | None = None,
        error: Exception | None = None,
        stream_responses: tuple[OllamaChatStreamResponse, ...] | None = None,
    ) -> None:
        self._response = response or _ollama_response()
        self._embedding_response = embedding_response or _ollama_embedding_response()
        self._error = error
        self._stream_responses = stream_responses or _ollama_stream_responses()
        self.calls: list[OllamaChatTransportRequest] = []
        self.embedding_calls: list[OllamaEmbeddingTransportRequest] = []

    async def post_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> OllamaChatResponse:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return self._response

    async def post_embedding_json(
        self,
        request: OllamaEmbeddingTransportRequest,
    ) -> OllamaEmbeddingResponse:
        self.embedding_calls.append(request)
        if self._error is not None:
            raise self._error
        return self._embedding_response

    async def stream_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> AsyncIterator[OllamaChatStreamResponse]:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        for response in self._stream_responses:
            yield response


class SequencedOllamaTransport:
    def __init__(self, outcomes: list[OllamaChatResponse | Exception]) -> None:
        self._outcomes = outcomes
        self.calls: list[OllamaChatTransportRequest] = []

    async def post_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> OllamaChatResponse:
        self.calls.append(request)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def post_embedding_json(
        self,
        request: OllamaEmbeddingTransportRequest,
    ) -> OllamaEmbeddingResponse:
        raise AssertionError("embedding requests are not used by retry tests")

    async def stream_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> AsyncIterator[OllamaChatStreamResponse]:
        if request.path:
            raise AssertionError("stream requests are not used by retry tests")
        yield _ollama_stream_responses()[0]


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        llm_timeout_seconds=12,
        ollama_chat_model="llama3.1",
    )


def _generation_request(
    *,
    model: str | None = None,
    response_format: LLMResponseFormat = LLMResponseFormat.TEXT,
    options: LLMGenerationOptions | None = None,
) -> LLMGenerationRequest:
    return LLMGenerationRequest(
        messages=(
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content="Classify only with grounded evidence.",
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content="Return the category for this synthetic job email.",
            ),
        ),
        model=model,
        response_format=response_format,
        options=options or LLMGenerationOptions(),
    )


def _ollama_response(
    *,
    content: str = "application_confirmation",
    model: str = "llama3.1",
    done_reason: str = "stop",
) -> OllamaChatResponse:
    return OllamaChatResponse.model_validate(
        {
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": done_reason,
            "prompt_eval_count": 7,
            "eval_count": 11,
        }
    )


def _ollama_embedding_response(
    *,
    model: str = "nomic-embed-text",
) -> OllamaEmbeddingResponse:
    return OllamaEmbeddingResponse.model_validate(
        {
            "model": model,
            "embeddings": [list(EMBEDDING_1536), list(EMBEDDING_1536)],
            "prompt_eval_count": 13,
        }
    )


def _ollama_stream_responses() -> tuple[OllamaChatStreamResponse, ...]:
    return (
        OllamaChatStreamResponse.model_validate(
            {
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "application_"},
                "done": False,
            }
        ),
        OllamaChatStreamResponse.model_validate(
            {
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "confirmation"},
                "done": False,
            }
        ),
        OllamaChatStreamResponse.model_validate(
            {
                "model": "llama3.1",
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 7,
                "eval_count": 11,
            }
        ),
    )


def test_ollama_provider_satisfies_protocol_and_builds_chat_payload() -> None:
    transport = FakeOllamaTransport()
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    response = asyncio.run(
        provider.generate(
            _generation_request(
                options=LLMGenerationOptions(temperature=0.2, max_output_tokens=128),
            )
        )
    )

    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, LLMEmbeddingProvider)
    assert provider.provider_name == "ollama"
    assert response.content == "application_confirmation"
    assert response.model == "llama3.1"
    assert response.finish_reason is LLMFinishReason.STOP
    assert response.usage == LLMTokenUsage(
        prompt_tokens=7,
        completion_tokens=11,
        total_tokens=18,
    )

    assert len(transport.calls) == 1
    transport_request = transport.calls[0]
    payload = transport_request.payload.model_dump(exclude_none=True, mode="json")
    assert transport_request.path == "/api/chat"
    assert transport_request.timeout_seconds == 12
    assert payload["model"] == "llama3.1"
    assert payload["stream"] is False
    assert payload["messages"] == [
        {"role": "system", "content": "Classify only with grounded evidence."},
        {
            "role": "user",
            "content": "Return the category for this synthetic job email.",
        },
    ]
    assert "format" not in payload
    assert cast(dict[str, object], payload["options"]) == {
        "temperature": 0.2,
        "num_predict": 128,
    }


def test_ollama_provider_uses_request_model_override_and_json_format() -> None:
    transport = FakeOllamaTransport(response=_ollama_response(model="mistral"))
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    response = asyncio.run(
        provider.generate(
            _generation_request(
                model="mistral",
                response_format=LLMResponseFormat.JSON_OBJECT,
            )
        )
    )

    assert response.model == "mistral"
    payload = transport.calls[0].payload.model_dump(exclude_none=True, mode="json")
    assert payload["model"] == "mistral"
    assert payload["format"] == "json"
    assert "options" not in payload


def test_ollama_provider_streams_ndjson_deltas_and_final_metadata() -> None:
    transport = FakeOllamaTransport()
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    async def collect() -> list[LLMGenerationChunk]:
        return [
            chunk
            async for chunk in provider.stream_generate(
                _generation_request(response_format=LLMResponseFormat.JSON_OBJECT)
            )
        ]

    chunks = asyncio.run(collect())

    assert [chunk.content_delta for chunk in chunks] == [
        "application_",
        "confirmation",
        "",
    ]
    assert chunks[-1].finish_reason is LLMFinishReason.STOP
    assert chunks[-1].usage == LLMTokenUsage(
        prompt_tokens=7,
        completion_tokens=11,
        total_tokens=18,
    )
    payload = transport.calls[0].payload.model_dump(exclude_none=True, mode="json")
    assert payload["stream"] is True
    assert payload["format"] == "json"


def test_ollama_provider_rejects_stream_without_final_record() -> None:
    provider = OllamaLLMProvider(
        settings=_settings(),
        transport=FakeOllamaTransport(
            stream_responses=(
                OllamaChatStreamResponse.model_validate(
                    {
                        "model": "llama3.1",
                        "message": {"role": "assistant", "content": "partial"},
                        "done": False,
                    }
                ),
            )
        ),
    )

    async def collect() -> list[LLMGenerationChunk]:
        return [chunk async for chunk in provider.stream_generate(_generation_request())]

    with pytest.raises(LLMProviderResponseError):
        asyncio.run(collect())


def test_ollama_provider_maps_stream_timeout_without_content() -> None:
    provider = OllamaLLMProvider(
        settings=AppSettings(_env_file=None, llm_max_retries=0),
        transport=FakeOllamaTransport(error=OllamaTransportTimeoutError()),
    )

    async def collect() -> list[LLMGenerationChunk]:
        return [chunk async for chunk in provider.stream_generate(_generation_request())]

    with pytest.raises(LLMProviderTimeoutError):
        asyncio.run(collect())


def test_ollama_provider_posts_embedding_request() -> None:
    transport = FakeOllamaTransport()
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    response = asyncio.run(
        provider.embed(
            LLMEmbeddingRequest(
                inputs=("first retained chunk", "second retained chunk"),
            )
        )
    )

    assert len(transport.embedding_calls) == 1
    transport_request = transport.embedding_calls[0]
    payload = transport_request.payload.model_dump(mode="json")
    assert transport_request.path == "/api/embed"
    assert transport_request.timeout_seconds == 12
    assert payload == {
        "model": "nomic-embed-text",
        "input": ["first retained chunk", "second retained chunk"],
    }
    assert response.model == "nomic-embed-text"
    assert response.embeddings == (
        LLMEmbedding(index=0, embedding=EMBEDDING_1536),
        LLMEmbedding(index=1, embedding=EMBEDDING_1536),
    )
    assert response.usage == LLMTokenUsage(prompt_tokens=13, total_tokens=13)


def test_ollama_provider_health_check_reports_configured_models_available() -> None:
    transport = FakeOllamaTransport()
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    response = asyncio.run(
        provider.health_check(
            LLMProviderHealthCheckRequest(
                chat_model="llama3.1",
                embedding_model="nomic-embed-text",
            )
        )
    )

    assert len(transport.embedding_calls) == 1
    assert transport.embedding_calls[0].payload.model == "nomic-embed-text"
    assert transport.embedding_calls[0].payload.input == ("Health check.",)
    assert response.provider_name == "ollama"
    assert response.status is LLMModelHealthStatus.AVAILABLE
    assert [(check.kind, check.model, check.status) for check in response.checks] == [
        (LLMModelKind.CHAT, "llama3.1", LLMModelHealthStatus.AVAILABLE),
        (
            LLMModelKind.EMBEDDING,
            "nomic-embed-text",
            LLMModelHealthStatus.AVAILABLE,
        ),
    ]


def test_ollama_provider_maps_length_finish_reason() -> None:
    transport = FakeOllamaTransport(response=_ollama_response(done_reason="length"))
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    response = asyncio.run(provider.generate(_generation_request()))

    assert response.finish_reason is LLMFinishReason.LENGTH


def test_ollama_provider_retries_transient_transport_failures() -> None:
    transport = SequencedOllamaTransport(
        [
            OllamaTransportTimeoutError(),
            OllamaTransportError(status_code=503),
            _ollama_response(),
        ]
    )
    provider = OllamaLLMProvider(
        settings=AppSettings(
            _env_file=None,
            llm_max_retries=2,
        ),
        transport=transport,
    )

    response = asyncio.run(provider.generate(_generation_request()))

    assert response.content == "application_confirmation"
    assert len(transport.calls) == 3


def test_ollama_provider_rejects_invalid_response_without_private_payload() -> None:
    transport = FakeOllamaTransport(error=OllamaTransportInvalidResponseError())
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    with pytest.raises(LLMProviderResponseError) as error_info:
        asyncio.run(provider.generate(_generation_request()))

    assert error_info.value.public_message == "Ollama returned invalid generation data."
    assert "synthetic job email" not in str(error_info.value)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://ollama.example.com",
        "http://192.0.2.10:11434",
    ],
)
def test_ollama_provider_rejects_non_local_base_url(base_url: str) -> None:
    transport = FakeOllamaTransport()

    with pytest.raises(LLMProviderUnavailableError) as error_info:
        OllamaLLMProvider(
            settings=AppSettings(_env_file=None, ollama_base_url=base_url),
            transport=transport,
        )

    assert error_info.value.public_message == "Ollama base URL must point to a local host."
    assert transport.calls == []


def test_llm_provider_dependency_resolves_selected_ollama_provider() -> None:
    from app.api.dependencies import get_llm_provider

    provider = get_llm_provider(AppSettings(_env_file=None), FakeSecretStore())

    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, OllamaLLMProvider)
    assert provider.provider_name == "ollama"


def test_llm_provider_dependency_maps_invalid_ollama_config_to_api_error() -> None:
    from app.api.dependencies import get_llm_provider
    from app.api.errors import ApiError, ApiErrorCode

    with pytest.raises(ApiError) as error_info:
        get_llm_provider(
            AppSettings(
                _env_file=None,
                ollama_base_url="https://ollama.example.com",
            ),
            FakeSecretStore(),
        )

    assert error_info.value.status_code == 400
    assert error_info.value.code is ApiErrorCode.BAD_REQUEST
    assert error_info.value.message == "Ollama base URL must point to a local host."


def test_urllib_transport_builds_proxy_disabled_opener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy_handlers: list[FakeProxyHandler] = []

    class FakeOpener:
        pass

    def fake_build_opener(handler: FakeProxyHandler) -> FakeOpener:
        proxy_handlers.append(handler)
        return FakeOpener()

    monkeypatch.setattr("app.providers.llm.ollama.ProxyHandler", FakeProxyHandler)
    monkeypatch.setattr("app.providers.llm.ollama.build_opener", fake_build_opener)

    UrllibOllamaTransport(base_url="http://127.0.0.1:11434")

    assert [handler.proxies for handler in proxy_handlers] == [{}]


@pytest.mark.parametrize(
    ("transport_error", "expected_error", "public_message"),
    [
        (
            OllamaTransportTimeoutError(),
            LLMProviderTimeoutError,
            "Ollama request timed out.",
        ),
        (
            OllamaTransportError(status_code=503),
            LLMProviderUnavailableError,
            "Ollama is unavailable.",
        ),
        (
            OllamaTransportError(status_code=400),
            LLMProviderRequestError,
            "Ollama request failed.",
        ),
    ],
)
def test_ollama_provider_maps_transport_errors(
    transport_error: Exception,
    expected_error: type[Exception],
    public_message: str,
) -> None:
    provider = OllamaLLMProvider(
        settings=_settings(),
        transport=FakeOllamaTransport(error=transport_error),
    )

    with pytest.raises(expected_error) as error_info:
        asyncio.run(provider.generate(_generation_request()))

    assert str(error_info.value) == public_message
    assert "synthetic job email" not in str(error_info.value)


class FakeProxyHandler:
    def __init__(self, proxies: dict[str, str]) -> None:
        self.proxies = proxies
