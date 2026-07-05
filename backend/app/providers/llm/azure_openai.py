from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import NoReturn, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.config import AppSettings, LLMProviderName
from app.providers.llm.errors import (
    LLMProviderError,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from app.providers.llm.types import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMResponseFormat,
    LLMTokenUsage,
)
from app.security import SecretKind, SecretRef, SecretStore, SecretStoreUnavailableError

_AZURE_OPENAI_API_KEY_REF = SecretRef(
    kind=SecretKind.LLM_API_KEY,
    provider="azure_openai",
    name="api_key",
)
_TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_INVALID_RESPONSE_MESSAGE = "Azure OpenAI returned an invalid response."
_HEALTH_CHECK_PROMPT = "Health check. Reply OK."
_EMBEDDING_HEALTH_DETAIL = "Azure OpenAI embedding health checks are not implemented yet."


class AzureOpenAIChatMessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    content: str | None = None


class AzureOpenAIChatChoiceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    message: AzureOpenAIChatMessageResponse
    finish_reason: str | None = None


class AzureOpenAIUsageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class AzureOpenAIChatCompletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    choices: tuple[AzureOpenAIChatChoiceResponse, ...] = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    usage: AzureOpenAIUsageResponse | None = None


class AzureOpenAITransport(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """POST JSON to Azure OpenAI without exposing API key material."""
        ...


@dataclass(frozen=True)
class AzureOpenAITransportError(RuntimeError):
    status_code: int | None
    reason: str | None = None
    is_timeout: bool = False


class UrllibAzureOpenAITransport:
    async def post_json(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        return await asyncio.to_thread(
            self._post_json_sync,
            url,
            api_key=api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def _post_json_sync(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "api-key": api_key.get_secret_value(),
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as error:
            raise AzureOpenAITransportError(
                status_code=error.code,
                reason=error.reason,
            ) from error
        except TimeoutError as error:
            raise AzureOpenAITransportError(
                status_code=None,
                reason="timeout",
                is_timeout=True,
            ) from error
        except URLError as error:
            raise AzureOpenAITransportError(
                status_code=None,
                reason=str(error.reason),
                is_timeout=isinstance(error.reason, TimeoutError),
            ) from error

        try:
            raw_response = response_body.decode("utf-8")
            decoded_response = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE) from None

        if not isinstance(decoded_response, dict):
            raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE)
        return cast(dict[str, object], decoded_response)


class AzureOpenAIProvider:
    """Azure OpenAI chat-completions adapter for provider-neutral LLM generation."""

    provider_name = LLMProviderName.AZURE_OPENAI.value

    def __init__(
        self,
        *,
        settings: AppSettings,
        secret_store: SecretStore | None,
        transport: AzureOpenAITransport | None = None,
    ) -> None:
        self._endpoint = settings.azure_openai_endpoint.strip().rstrip("/")
        self._api_version = settings.azure_openai_api_version.strip()
        self._chat_deployment = settings.azure_openai_chat_deployment.strip()
        self._timeout_seconds = settings.llm_timeout_seconds
        self._secret_store = secret_store
        self._transport = transport or UrllibAzureOpenAITransport()

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        deployment = (request.model or self._chat_deployment).strip()
        if not self._endpoint or not self._api_version or not deployment:
            raise LLMProviderUnavailableError(
                public_message="Azure OpenAI provider is not configured."
            )

        api_key = await self._read_api_key()
        try:
            response_payload = await self._transport.post_json(
                _chat_completions_url(
                    endpoint=self._endpoint,
                    deployment=deployment,
                    api_version=self._api_version,
                ),
                api_key=api_key,
                payload=_chat_completion_payload(request),
                timeout_seconds=self._timeout_seconds,
            )
        except AzureOpenAITransportError as error:
            _raise_provider_error_for_transport_error(error)

        try:
            azure_response = AzureOpenAIChatCompletionResponse.model_validate(response_payload)
        except ValidationError as error:
            raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE) from error

        choice = azure_response.choices[0]
        finish_reason = _finish_reason(choice.finish_reason)
        content = _completion_content(choice, finish_reason)
        return LLMGenerationResponse(
            content=content,
            model=azure_response.model or deployment,
            finish_reason=finish_reason,
            usage=_token_usage(azure_response.usage),
        )

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        chat_check = await self._chat_health_check(request.chat_model)
        embedding_check = LLMModelHealthCheck(
            kind=LLMModelKind.EMBEDDING,
            model=request.embedding_model,
            status=LLMModelHealthStatus.UNAVAILABLE,
            detail=_EMBEDDING_HEALTH_DETAIL,
        )
        return LLMProviderHealthCheckResponse(
            provider_name=self.provider_name,
            status=_health_status((chat_check, embedding_check)),
            checks=(chat_check, embedding_check),
        )

    async def _chat_health_check(self, model: str) -> LLMModelHealthCheck:
        try:
            await self.generate(
                LLMGenerationRequest(
                    messages=(
                        LLMMessage(role=LLMMessageRole.USER, content=_HEALTH_CHECK_PROMPT),
                    ),
                    model=model,
                    options=LLMGenerationOptions(max_output_tokens=1),
                )
            )
        except LLMProviderError as error:
            return LLMModelHealthCheck(
                kind=LLMModelKind.CHAT,
                model=model,
                status=LLMModelHealthStatus.UNAVAILABLE,
                detail=error.public_message,
            )
        return LLMModelHealthCheck(
            kind=LLMModelKind.CHAT,
            model=model,
            status=LLMModelHealthStatus.AVAILABLE,
        )

    async def _read_api_key(self) -> SecretStr:
        if self._secret_store is None:
            raise LLMProviderUnavailableError(
                public_message="Azure OpenAI API key is not configured."
            )

        try:
            api_key = await self._secret_store.get_secret(_AZURE_OPENAI_API_KEY_REF)
        except SecretStoreUnavailableError as error:
            raise LLMProviderUnavailableError(
                public_message="Azure OpenAI API key storage is unavailable."
            ) from error

        if api_key is None or not api_key.get_secret_value().strip():
            raise LLMProviderUnavailableError(
                public_message="Azure OpenAI API key is not configured."
            )
        return SecretStr(api_key.get_secret_value().strip())


def _chat_completion_payload(request: LLMGenerationRequest) -> dict[str, object]:
    payload: dict[str, object] = {
        "messages": [message.model_dump(mode="json") for message in request.messages]
    }
    if request.options.temperature is not None:
        payload["temperature"] = request.options.temperature
    if request.options.max_output_tokens is not None:
        payload["max_tokens"] = request.options.max_output_tokens
    if request.response_format is LLMResponseFormat.JSON_OBJECT:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _chat_completions_url(*, endpoint: str, deployment: str, api_version: str) -> str:
    query = urlencode({"api-version": api_version})
    encoded_deployment = quote(deployment, safe="")
    return f"{endpoint}/openai/deployments/{encoded_deployment}/chat/completions?{query}"


def _finish_reason(raw_finish_reason: str | None) -> LLMFinishReason:
    if raw_finish_reason == "stop":
        return LLMFinishReason.STOP
    if raw_finish_reason == "length":
        return LLMFinishReason.LENGTH
    if raw_finish_reason == "content_filter":
        return LLMFinishReason.CONTENT_FILTER
    if raw_finish_reason in {"tool_calls", "function_call"}:
        return LLMFinishReason.TOOL_CALL
    if raw_finish_reason == "error":
        return LLMFinishReason.ERROR
    return LLMFinishReason.UNKNOWN


def _completion_content(
    choice: AzureOpenAIChatChoiceResponse,
    finish_reason: LLMFinishReason,
) -> str:
    content = choice.message.content
    if content:
        return content
    if finish_reason is LLMFinishReason.CONTENT_FILTER:
        return ""
    raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE)


def _token_usage(usage: AzureOpenAIUsageResponse | None) -> LLMTokenUsage | None:
    if usage is None:
        return None
    return LLMTokenUsage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )


def _health_status(
    checks: tuple[LLMModelHealthCheck, ...],
) -> LLMModelHealthStatus:
    if any(check.status is LLMModelHealthStatus.UNAVAILABLE for check in checks):
        return LLMModelHealthStatus.UNAVAILABLE
    return LLMModelHealthStatus.AVAILABLE


def _raise_provider_error_for_transport_error(error: AzureOpenAITransportError) -> NoReturn:
    if error.is_timeout or error.reason == "timeout":
        raise LLMProviderTimeoutError(public_message="Azure OpenAI request timed out.") from error
    if error.status_code is None or error.status_code in _TRANSIENT_STATUS_CODES:
        raise LLMProviderUnavailableError(
            public_message="Azure OpenAI is temporarily unavailable."
        ) from error
    raise LLMProviderRequestError(public_message="Azure OpenAI request failed.") from error


__all__ = [
    "AzureOpenAIProvider",
    "AzureOpenAITransport",
    "AzureOpenAITransportError",
    "UrllibAzureOpenAITransport",
]
