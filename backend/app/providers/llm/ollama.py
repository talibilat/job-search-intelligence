from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import OpenerDirector, ProxyHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import AppSettings, LLMProviderName

from .errors import (
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from .types import (
    LLMEmbedding,
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
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

_OLLAMA_CHAT_PATH = "/api/chat"
_OLLAMA_EMBED_PATH = "/api/embed"
_OLLAMA_JSON_FORMAT = "json"
_EMBEDDING_HEALTH_INPUT = "Health check."
_INVALID_RESPONSE_MESSAGE = "Ollama returned invalid generation data."


class OllamaTransport(Protocol):
    async def post_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> OllamaChatResponse:
        """POST a JSON request to Ollama without logging prompt content."""
        ...

    async def post_embedding_json(
        self,
        request: OllamaEmbeddingTransportRequest,
    ) -> OllamaEmbeddingResponse:
        """POST an embedding request to Ollama without logging retained text."""
        ...


@dataclass(frozen=True)
class OllamaTransportError(RuntimeError):
    status_code: int | None = None


class OllamaTransportTimeoutError(RuntimeError):
    pass


class OllamaTransportInvalidResponseError(RuntimeError):
    pass


class UrllibOllamaTransport:
    def __init__(self, *, base_url: str, opener: OpenerDirector | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._opener = opener or build_opener(ProxyHandler({}))

    async def post_json(
        self,
        request: OllamaChatTransportRequest,
    ) -> OllamaChatResponse:
        return await asyncio.to_thread(
            self._post_json_sync,
            request,
        )

    async def post_embedding_json(
        self,
        request: OllamaEmbeddingTransportRequest,
    ) -> OllamaEmbeddingResponse:
        return await asyncio.to_thread(
            self._post_embedding_json_sync,
            request,
        )

    def _post_json_sync(
        self,
        transport_request: OllamaChatTransportRequest,
    ) -> OllamaChatResponse:
        http_request = Request(
            _join_ollama_url(self._base_url, transport_request.path),
            data=json.dumps(
                transport_request.payload.model_dump(exclude_none=True, mode="json"),
                separators=(",", ":"),
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self._opener.open(
                http_request,
                timeout=transport_request.timeout_seconds,
            ) as response:
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
        try:
            return OllamaChatResponse.model_validate(cast(dict[str, object], decoded_response))
        except ValidationError:
            raise OllamaTransportInvalidResponseError from None

    def _post_embedding_json_sync(
        self,
        transport_request: OllamaEmbeddingTransportRequest,
    ) -> OllamaEmbeddingResponse:
        http_request = Request(
            _join_ollama_url(self._base_url, transport_request.path),
            data=json.dumps(
                transport_request.payload.model_dump(mode="json"),
                separators=(",", ":"),
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self._opener.open(
                http_request,
                timeout=transport_request.timeout_seconds,
            ) as response:
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
        try:
            return OllamaEmbeddingResponse.model_validate(cast(dict[str, object], decoded_response))
        except ValidationError:
            raise OllamaTransportInvalidResponseError from None


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


class OllamaChatTransportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    payload: OllamaChatRequestPayload
    timeout_seconds: int = Field(ge=1)


class OllamaEmbeddingRequestPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    input: tuple[str, ...] = Field(min_length=1, repr=False)


class OllamaEmbeddingTransportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    payload: OllamaEmbeddingRequestPayload
    timeout_seconds: int = Field(ge=1)


class OllamaEmbeddingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    model: str | None = Field(default=None, min_length=1)
    embeddings: tuple[tuple[float, ...], ...] = Field(min_length=1, repr=False)
    prompt_eval_count: int | None = Field(default=None, ge=0)


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
        _validate_local_base_url(settings.ollama_base_url)
        self._chat_model = settings.ollama_chat_model
        self._embedding_model = settings.ollama_embedding_model
        self._timeout_seconds = settings.llm_timeout_seconds
        self._max_retries = settings.llm_max_retries
        self._transport = transport or UrllibOllamaTransport(base_url=settings.ollama_base_url)

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        transport_request = OllamaChatTransportRequest(
            path=_OLLAMA_CHAT_PATH,
            payload=_chat_request_payload(request, default_model=self._chat_model),
            timeout_seconds=self._timeout_seconds,
        )
        for attempt_index in range(self._max_retries + 1):
            try:
                response = await self._transport.post_json(transport_request)
                break
            except OllamaTransportTimeoutError as error:
                if attempt_index < self._max_retries:
                    continue
                raise LLMProviderTimeoutError(public_message="Ollama request timed out.") from error
            except OllamaTransportInvalidResponseError as error:
                raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE) from error
            except OllamaTransportError as error:
                if _is_unavailable_status(error.status_code):
                    if attempt_index < self._max_retries:
                        continue
                    raise LLMProviderUnavailableError(
                        public_message="Ollama is unavailable."
                    ) from error
                raise LLMProviderRequestError(public_message="Ollama request failed.") from error

        return _generation_response(response)

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        transport_request = OllamaEmbeddingTransportRequest(
            path=_OLLAMA_EMBED_PATH,
            payload=OllamaEmbeddingRequestPayload(
                model=request.model or self._embedding_model,
                input=request.inputs,
            ),
            timeout_seconds=self._timeout_seconds,
        )
        for attempt_index in range(self._max_retries + 1):
            try:
                response = await self._transport.post_embedding_json(transport_request)
                break
            except OllamaTransportTimeoutError as error:
                if attempt_index < self._max_retries:
                    continue
                raise LLMProviderTimeoutError(public_message="Ollama request timed out.") from error
            except OllamaTransportInvalidResponseError as error:
                raise LLMProviderResponseError(public_message=_INVALID_RESPONSE_MESSAGE) from error
            except OllamaTransportError as error:
                if _is_unavailable_status(error.status_code):
                    if attempt_index < self._max_retries:
                        continue
                    raise LLMProviderUnavailableError(
                        public_message="Ollama is unavailable."
                    ) from error
                raise LLMProviderRequestError(public_message="Ollama request failed.") from error

        return LLMEmbeddingResponse(
            model=response.model or transport_request.payload.model,
            embeddings=tuple(
                LLMEmbedding(index=index, embedding=embedding)
                for index, embedding in enumerate(response.embeddings)
            ),
            usage=_embedding_token_usage(response),
        )

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        await self.generate(
            LLMGenerationRequest(
                messages=(
                    LLMMessage(role=LLMMessageRole.SYSTEM, content="Health check."),
                    LLMMessage(role=LLMMessageRole.USER, content="Reply with ok."),
                ),
                model=request.chat_model,
                options=LLMGenerationOptions(temperature=0, max_output_tokens=4),
            )
        )
        await self.embed(
            LLMEmbeddingRequest(
                inputs=(_EMBEDDING_HEALTH_INPUT,),
                model=request.embedding_model,
            )
        )
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
        format=(
            _OLLAMA_JSON_FORMAT
            if request.response_format is LLMResponseFormat.JSON_OBJECT
            else None
        ),
        options=(
            None
            if request.options.temperature is None and request.options.max_output_tokens is None
            else OllamaRequestOptions(
                temperature=request.options.temperature,
                num_predict=request.options.max_output_tokens,
            )
        ),
    )


def _generation_response(response: OllamaChatResponse) -> LLMGenerationResponse:
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


def _embedding_token_usage(response: OllamaEmbeddingResponse) -> LLMTokenUsage | None:
    if response.prompt_eval_count is None:
        return None
    return LLMTokenUsage(
        prompt_tokens=response.prompt_eval_count,
        total_tokens=response.prompt_eval_count,
    )


def _health_status(
    checks: tuple[LLMModelHealthCheck, ...],
) -> LLMModelHealthStatus:
    if any(check.status is LLMModelHealthStatus.UNAVAILABLE for check in checks):
        return LLMModelHealthStatus.UNAVAILABLE
    return LLMModelHealthStatus.AVAILABLE


def _is_unavailable_status(status_code: int | None) -> bool:
    return status_code is None or status_code in {408, 429, 500, 502, 503, 504}


def _join_ollama_url(base_url: str, path: str) -> str:
    if path.startswith("/"):
        return f"{base_url}{path}"
    return f"{base_url}/{path}"


def _validate_local_base_url(base_url: str) -> None:
    if not is_local_ollama_base_url(base_url):
        raise LLMProviderUnavailableError(
            public_message="Ollama base URL must point to a local host."
        )


def is_local_ollama_base_url(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and _is_local_hostname(parsed.hostname)
    )


def _is_local_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False
