from __future__ import annotations

import asyncio

import pytest
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMProvider,
    LLMProviderError,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
    LLMTokenUsage,
)
from pydantic import BaseModel, ValidationError


class FakeLLMProvider:
    provider_name = "fake"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        return LLMGenerationResponse(
            content=request.messages[-1].content,
            model=request.model or "fake-model",
            finish_reason=LLMFinishReason.STOP,
            usage=LLMTokenUsage(
                prompt_tokens=3,
                completion_tokens=5,
                total_tokens=8,
            ),
        )


def test_fake_provider_satisfies_llm_provider_protocol() -> None:
    assert isinstance(FakeLLMProvider(), LLMProvider)


def test_llm_provider_generation_round_trip() -> None:
    provider = FakeLLMProvider()
    request = LLMGenerationRequest(
        messages=(
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content="Answer using only grounded context.",
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content="Summarize this application event.",
            ),
        ),
        model="fake-chat-model",
        response_format=LLMResponseFormat.TEXT,
        options=LLMGenerationOptions(
            temperature=0,
            max_output_tokens=256,
        ),
    )

    response = asyncio.run(provider.generate(request))

    assert response.content == "Summarize this application event."
    assert response.model == "fake-chat-model"
    assert response.finish_reason is LLMFinishReason.STOP
    assert response.usage == LLMTokenUsage(
        prompt_tokens=3,
        completion_tokens=5,
        total_tokens=8,
    )


def test_generation_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        LLMGenerationRequest(messages=())


def test_generation_message_requires_content() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role=LLMMessageRole.USER, content="")


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_generation_options_reject_out_of_range_temperature(
    temperature: float,
) -> None:
    with pytest.raises(ValidationError):
        LLMGenerationOptions(temperature=temperature)


def test_generation_options_reject_non_positive_max_output_tokens() -> None:
    with pytest.raises(ValidationError):
        LLMGenerationOptions(max_output_tokens=0)


def test_token_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        LLMTokenUsage(prompt_tokens=-1)


def test_llm_provider_errors_are_typed() -> None:
    errors = [
        LLMProviderUnavailableError("provider is unavailable"),
        LLMProviderRequestError("provider request failed"),
        LLMProviderResponseError("provider response was invalid"),
        LLMProviderTimeoutError("provider request timed out"),
    ]

    assert all(isinstance(error, LLMProviderError) for error in errors)


def test_llm_boundary_models_do_not_define_credential_fields() -> None:
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
        LLMMessage,
        LLMGenerationOptions,
        LLMGenerationRequest,
        LLMGenerationResponse,
    )

    for model in boundary_models:
        assert credential_field_names.isdisjoint(model.model_fields)
