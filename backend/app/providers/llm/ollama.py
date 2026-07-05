from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import AppSettings, LLMProviderName

from .errors import (
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from .types import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMResponseFormat,
    LLMTokenUsage,
)

_OLLAMA_CHAT_PATH = "/api/chat"
_OLLAMA_JSON_FORMAT = "json"
_INVALID_RESPONSE_MESSAGE = "Ollama returned invalid generation data."


class OllamaTransport(Protocol):
    async def post_json(
        self,
        path: str,
        *,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """POST a JSON request to Ollama without logging prompt content."""
        ...


@dataclass(frozen=True)
class OllamaTransportError(RuntimeError):
    status_code: int | None = None


class OllamaTransportTimeoutError(RuntimeError):
    pass


class OllamaTransportInvalidResponseError(RuntimeError):
    pass


class UrllibOllamaTransport:
    def __init__(self, *, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def post_json(
        self,
        path: str,
        *,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        return await asyncio.to_thread(
            self._post_json_sync,
            path,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def _post_json_sync(
        self,
        path: str,
        *,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        request = Request(
            _join_ollama_url(self._base_url, path),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read()
        except TimeoutError as error:
            raise OllamaTransportTimeoutError from error
        except HTTPError as error:
            raise OllamaTransportError(status_code=error.code) from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise OllamaTransportTimeoutError from error
            raise OllamaTransportError(status_code=None) from error

        try:
            decoded_response = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OllamaTransportInvalidResponseError from error

        if not isinstance(decoded_response, dict):
            raise OllamaTransportInvalidResponseError
        return cast(dict[str, object], decoded_response)


class OllamaChatMessagePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class OllamaRequestOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    temperature: float | None = Field(default=None, ge=0, le=2)
    num_predict: int | None = Field(default=None, ge=1)


class OllamaChatRequestPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    messages: tuple[OllamaChatMessagePayload, ...] = Field(min_length=1)
    stream: bool = False
    format: str | None = Field(default=None, min_length=1)
    options: OllamaRequestOptions | None = None


class OllamaChatResponseMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class OllamaChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    model: str = Field(min_length=1)
    message: OllamaChatResponseMessage
    done: bool
    done_reason: str | None = None
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)


class OllamaLLMProvider:
    """Local Ollama chat adapter for provider-neutral LLM generation."""

    provider_name = LLMProviderName.OLLAMA.value

    def __init__(
        self,
        *,
        settings: AppSettings,
        transport: OllamaTransport | None = None,
    ) -> None:
        self._chat_model = settings.ollama_chat_model
        self._timeout_seconds = settings.llm_timeout_seconds
        self._transport = transport or UrllibOllamaTransport(base_url=settings.ollama_base_url)

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        payload = _chat_request_payload(request, default_model=self._chat_model).model_dump(
            exclude_none=True,
            mode="json",
        )
        try:
            response_payload = await self._transport.post_json(
                _OLLAMA_CHAT_PATH,
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        except OllamaTransportTimeoutError as error:
            raise LLMProviderTimeoutError(public_message="Ollama request timed out.") from error
        except OllamaTransportInvalidResponseError as error:
            raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE) from error
        except OllamaTransportError as error:
            if _is_unavailable_status(error.status_code):
                raise LLMProviderUnavailableError(
                    public_message="Ollama is unavailable."
                ) from error
            raise LLMProviderRequestError(public_message="Ollama request failed.") from error

        return _generation_response(response_payload)


def _chat_request_payload(
    request: LLMGenerationRequest,
    *,
    default_model: str,
) -> OllamaChatRequestPayload:
    return OllamaChatRequestPayload(
        model=request.model or default_model,
        messages=tuple(
            OllamaChatMessagePayload(role=message.role.value, content=message.content)
            for message in request.messages
        ),
        stream=False,
        format=_response_format(request.response_format),
        options=_request_options(request.options),
    )


def _response_format(response_format: LLMResponseFormat) -> str | None:
    if response_format is LLMResponseFormat.JSON_OBJECT:
        return _OLLAMA_JSON_FORMAT
    return None


def _request_options(options: LLMGenerationOptions) -> OllamaRequestOptions | None:
    if options.temperature is None and options.max_output_tokens is None:
        return None
    return OllamaRequestOptions(
        temperature=options.temperature,
        num_predict=options.max_output_tokens,
    )


def _generation_response(payload: dict[str, object]) -> LLMGenerationResponse:
    try:
        response = OllamaChatResponse.model_validate(payload)
    except ValidationError as error:
        raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE) from error

    if not response.done:
        raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE)

    return LLMGenerationResponse(
        content=response.message.content,
        model=response.model,
        finish_reason=_finish_reason(response.done_reason),
        usage=_token_usage(response),
    )


def _finish_reason(done_reason: str | None) -> LLMFinishReason:
    if done_reason == "stop":
        return LLMFinishReason.STOP
    if done_reason == "length":
        return LLMFinishReason.LENGTH
    return LLMFinishReason.UNKNOWN


def _token_usage(response: OllamaChatResponse) -> LLMTokenUsage | None:
    if response.prompt_eval_count is None and response.eval_count is None:
        return None

    prompt_tokens = response.prompt_eval_count or 0
    completion_tokens = response.eval_count or 0
    return LLMTokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def _is_unavailable_status(status_code: int | None) -> bool:
    return status_code is None or status_code in {408, 429, 500, 502, 503, 504}


def _join_ollama_url(base_url: str, path: str) -> str:
    if path.startswith("/"):
        return f"{base_url}{path}"
    return f"{base_url}/{path}"
