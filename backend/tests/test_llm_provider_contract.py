from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, get_type_hints

import pytest
from app.api.provider_config import get_configured_llm_provider
from app.providers.llm import (
    LLMEmbedding,
    LLMEmbeddingProvider,
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMFinishReason,
    LLMGenerationChunk,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProvider,
    LLMProviderError,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
    LLMTokenUsage,
)
from pydantic import BaseModel, ValidationError

EMBEDDING_1536 = tuple(0.001 for _ in range(1536))


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

    async def stream_generate(
        self,
        request: LLMGenerationRequest,
    ) -> AsyncIterator[LLMGenerationChunk]:
        model = request.model or "fake-model"
        yield LLMGenerationChunk(content_delta=request.messages[-1].content, model=model)
        yield LLMGenerationChunk(
            content_delta="",
            model=model,
            finish_reason=LLMFinishReason.STOP,
            usage=LLMTokenUsage(prompt_tokens=3, completion_tokens=5, total_tokens=8),
        )

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        return LLMEmbeddingResponse(
            model=request.model or "fake-embedding-model",
            embeddings=(LLMEmbedding(index=0, embedding=EMBEDDING_1536),),
            usage=LLMTokenUsage(prompt_tokens=4, total_tokens=4),
        )

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        return LLMProviderHealthCheckResponse(
            provider_name=self.provider_name,
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


class MissingHealthCheckLLMProvider:
    provider_name = "missing-health-check"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        return LLMGenerationResponse(
            content=request.messages[-1].content,
            model=request.model or "fake-model",
        )


class MissingEmbeddingLLMProvider:
    provider_name = "missing-embedding"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        return LLMGenerationResponse(
            content=request.messages[-1].content,
            model=request.model or "fake-model",
        )

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        return LLMProviderHealthCheckResponse(
            provider_name=self.provider_name,
            status=LLMModelHealthStatus.AVAILABLE,
            checks=(
                LLMModelHealthCheck(
                    kind=LLMModelKind.CHAT,
                    model=request.chat_model,
                    status=LLMModelHealthStatus.AVAILABLE,
                ),
            ),
        )


def test_fake_provider_satisfies_llm_provider_protocol() -> None:
    provider: LLMProvider = FakeLLMProvider()

    assert isinstance(provider, LLMProvider)


def test_fake_provider_satisfies_llm_embedding_provider_protocol() -> None:
    provider: LLMEmbeddingProvider = FakeLLMProvider()

    assert isinstance(provider, LLMEmbeddingProvider)


def test_llm_provider_protocol_requires_health_check() -> None:
    assert not isinstance(MissingHealthCheckLLMProvider(), LLMProvider)


def test_llm_provider_protocol_requires_embedding_generation() -> None:
    assert not isinstance(MissingEmbeddingLLMProvider(), LLMEmbeddingProvider)


def test_configured_llm_provider_dependency_returns_protocol() -> None:
    assert get_type_hints(get_configured_llm_provider)["return"] is LLMProvider


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


def test_llm_provider_stream_generation_round_trip() -> None:
    async def collect() -> list[LLMGenerationChunk]:
        provider = FakeLLMProvider()
        request = LLMGenerationRequest(
            messages=(LLMMessage(role=LLMMessageRole.USER, content="Grounded answer."),),
            model="fake-chat-model",
        )
        return [chunk async for chunk in provider.stream_generate(request)]

    chunks = asyncio.run(collect())

    assert chunks == [
        LLMGenerationChunk(content_delta="Grounded answer.", model="fake-chat-model"),
        LLMGenerationChunk(
            content_delta="",
            model="fake-chat-model",
            finish_reason=LLMFinishReason.STOP,
            usage=LLMTokenUsage(prompt_tokens=3, completion_tokens=5, total_tokens=8),
        ),
    ]


def test_generation_chunk_is_immutable_and_restricts_terminal_metadata() -> None:
    chunk = LLMGenerationChunk(content_delta="delta", model="fake-chat-model")

    with pytest.raises(ValidationError):
        chunk.content_delta = "changed"
    with pytest.raises(ValidationError):
        LLMGenerationChunk(content_delta="", model="fake-chat-model")
    with pytest.raises(ValidationError):
        LLMGenerationChunk(
            content_delta="delta",
            model="fake-chat-model",
            usage=LLMTokenUsage(total_tokens=1),
        )


def test_llm_provider_health_check_round_trip() -> None:
    provider = FakeLLMProvider()
    request = LLMProviderHealthCheckRequest(
        chat_model="fake-chat-model",
        embedding_model="fake-embedding-model",
    )

    response = asyncio.run(provider.health_check(request))

    assert response.provider_name == "fake"
    assert response.status is LLMModelHealthStatus.AVAILABLE
    assert response.checks == (
        LLMModelHealthCheck(
            kind=LLMModelKind.CHAT,
            model="fake-chat-model",
            status=LLMModelHealthStatus.AVAILABLE,
        ),
        LLMModelHealthCheck(
            kind=LLMModelKind.EMBEDDING,
            model="fake-embedding-model",
            status=LLMModelHealthStatus.AVAILABLE,
        ),
    )


def test_llm_provider_embedding_round_trip() -> None:
    provider = FakeLLMProvider()
    request = LLMEmbeddingRequest(
        inputs=("Retained recruiter email chunk.",),
        model="fake-embedding-model",
    )

    response = asyncio.run(provider.embed(request))

    assert response.model == "fake-embedding-model"
    assert response.embeddings == (LLMEmbedding(index=0, embedding=EMBEDDING_1536),)
    assert response.usage == LLMTokenUsage(prompt_tokens=4, total_tokens=4)


def test_generation_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        LLMGenerationRequest(messages=())


def test_embedding_request_requires_at_least_one_input_and_hides_content_from_repr() -> None:
    request = LLMEmbeddingRequest(inputs=("Private retained body text.",))

    assert "Private retained body text" not in repr(request)
    with pytest.raises(ValidationError):
        LLMEmbeddingRequest(inputs=())


def test_embedding_vector_requires_values_and_hides_values() -> None:
    embedding = LLMEmbedding(index=0, embedding=EMBEDDING_1536)

    assert "0.001" not in repr(embedding)
    with pytest.raises(ValidationError):
        LLMEmbedding(index=0, embedding=())


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
        LLMProviderUnavailableError(public_message="provider is unavailable"),
        LLMProviderRequestError(public_message="provider request failed"),
        LLMProviderResponseError(public_message="provider response was invalid"),
        LLMProviderTimeoutError(public_message="provider request timed out"),
    ]

    assert all(isinstance(error, LLMProviderError) for error in errors)


def test_llm_provider_errors_expose_only_public_message() -> None:
    error = LLMProviderRequestError(public_message="provider request failed")

    assert error.public_message == "provider request failed"
    assert str(error) == "provider request failed"
    assert error.args == ("provider request failed",)


def test_llm_provider_errors_reject_positional_messages() -> None:
    error_type: type[Any] = LLMProviderRequestError

    with pytest.raises(TypeError):
        error_type("raw provider payload")


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
        LLMGenerationChunk,
        LLMGenerationResponse,
        LLMEmbeddingRequest,
        LLMEmbeddingResponse,
        LLMEmbedding,
        LLMModelHealthCheck,
        LLMProviderHealthCheckRequest,
        LLMProviderHealthCheckResponse,
    )

    for model in boundary_models:
        assert credential_field_names.isdisjoint(model.model_fields)
