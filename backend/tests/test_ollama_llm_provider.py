from __future__ import annotations

import asyncio
from typing import cast

import pytest
from app.config import AppSettings
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMProvider,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
    LLMTokenUsage,
)
from app.providers.llm.ollama import (
    OllamaChatResponse,
    OllamaChatTransportRequest,
    OllamaLLMProvider,
    OllamaTransportError,
    OllamaTransportInvalidResponseError,
    OllamaTransportTimeoutError,
)


class FakeOllamaTransport:
    def __init__(
        self,
        *,
        response: OllamaChatResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response or _ollama_response()
        self._error = error
        self.calls: list[OllamaChatTransportRequest] = []

    async def post_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> OllamaChatResponse:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return self._response


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


def test_ollama_provider_maps_length_finish_reason() -> None:
    transport = FakeOllamaTransport(response=_ollama_response(done_reason="length"))
    provider = OllamaLLMProvider(settings=_settings(), transport=transport)

    response = asyncio.run(provider.generate(_generation_request()))

    assert response.finish_reason is LLMFinishReason.LENGTH


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
