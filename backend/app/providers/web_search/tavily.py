from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import NoReturn, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError

from app.config import AppSettings, WebSearchProviderName
from app.models.web_search import WebSearchRequest, WebSearchResponse, WebSearchResult
from app.security import TAVILY_API_KEY_REF, SecretStore, SecretStoreError

from .errors import (
    WebSearchAuthenticationError,
    WebSearchMalformedResponseError,
    WebSearchMissingCredentialError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)

_INVALID_RESPONSE = "Tavily returned an invalid response."


class TavilyResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    title: str = Field(min_length=1)
    url: HttpUrl
    content: str = Field(min_length=1)


class TavilyResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    results: tuple[TavilyResult, ...]


class TavilyTransport(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class TavilyTransportError(RuntimeError):
    status_code: int | None
    is_timeout: bool = False


class UrllibTavilyTransport:
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
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as error:
            raise TavilyTransportError(status_code=error.code) from error
        except TimeoutError as error:
            raise TavilyTransportError(status_code=None, is_timeout=True) from error
        except URLError as error:
            raise TavilyTransportError(
                status_code=None,
                is_timeout=isinstance(error.reason, TimeoutError),
            ) from error

        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WebSearchMalformedResponseError(public_message=_INVALID_RESPONSE) from None
        if not isinstance(decoded, dict):
            raise WebSearchMalformedResponseError(public_message=_INVALID_RESPONSE)
        return cast(dict[str, object], decoded)


class TavilyWebSearchProvider:
    """Tavily adapter that sends only a search query and bounded result count."""

    provider_name = WebSearchProviderName.TAVILY.value

    def __init__(
        self,
        *,
        settings: AppSettings,
        secret_store: SecretStore,
        transport: TavilyTransport | None = None,
    ) -> None:
        self._base_url = settings.tavily_base_url
        self._enabled = settings.web_search_enabled
        self._max_results = settings.web_search_max_results
        self._timeout_seconds = settings.web_search_timeout_seconds
        self._secret_store = secret_store
        self._transport = transport or UrllibTavilyTransport()

    async def search(self, request: WebSearchRequest) -> WebSearchResponse:
        if not self._enabled:
            raise WebSearchUnavailableError(
                public_message="Tavily web search is disabled. Enable it in Settings."
            )
        api_key = await self._read_api_key()
        try:
            payload = await self._transport.post_json(
                f"{self._base_url}/search",
                api_key=api_key,
                payload={
                    "query": request.query,
                    "max_results": min(request.max_results, self._max_results),
                },
                timeout_seconds=self._timeout_seconds,
            )
        except TavilyTransportError as error:
            _raise_provider_error(error)

        try:
            response = TavilyResponse.model_validate(payload)
            results = tuple(
                WebSearchResult(title=item.title, url=item.url, snippet=item.content)
                for item in response.results
            )
        except ValidationError as error:
            raise WebSearchMalformedResponseError(public_message=_INVALID_RESPONSE) from error
        return WebSearchResponse(results=results)

    async def _read_api_key(self) -> SecretStr:
        try:
            api_key = await self._secret_store.get_secret(TAVILY_API_KEY_REF)
        except SecretStoreError as error:
            raise WebSearchUnavailableError(
                public_message="Tavily credential storage is unavailable."
            ) from error
        if api_key is None or not api_key.get_secret_value().strip():
            raise WebSearchMissingCredentialError(
                public_message="Tavily API key is not configured."
            )
        return SecretStr(api_key.get_secret_value().strip())


def _raise_provider_error(error: TavilyTransportError) -> NoReturn:
    if error.is_timeout:
        raise WebSearchTimeoutError(public_message="Tavily request timed out.") from error
    if error.status_code in {401, 403}:
        raise WebSearchAuthenticationError(
            public_message="Tavily rejected the configured credential."
        ) from error
    if error.status_code == 429:
        raise WebSearchRateLimitError(public_message="Tavily rate limit was reached.") from error
    raise WebSearchUnavailableError(public_message="Tavily is temporarily unavailable.") from error


__all__ = [
    "TavilyTransport",
    "TavilyTransportError",
    "TavilyWebSearchProvider",
    "UrllibTavilyTransport",
]
