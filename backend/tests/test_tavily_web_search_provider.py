from __future__ import annotations

import asyncio

import pytest
from app.config import AppSettings
from app.models.web_search import WebSearchRequest
from app.providers.web_search import (
    TavilyWebSearchProvider,
    WebSearchAuthenticationError,
    WebSearchMalformedResponseError,
    WebSearchMissingCredentialError,
    WebSearchProvider,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)
from app.providers.web_search.tavily import TavilyTransportError
from app.security import TAVILY_API_KEY_REF, SecretRef
from pydantic import SecretStr, ValidationError


class MemorySecretStore:
    def __init__(self, value: str | None = "tavily-secret") -> None:
        self.value = value

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        assert ref == TAVILY_API_KEY_REF
        return SecretStr(self.value) if self.value is not None else None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        del ref


class RecordingTransport:
    def __init__(self, response: dict[str, object] | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, SecretStr, dict[str, object], int]] = []

    async def post_json(
        self,
        url: str,
        *,
        api_key: SecretStr,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.calls.append((url, api_key, payload, timeout_seconds))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_tavily_provider_sends_query_only_and_caps_results() -> None:
    transport = RecordingTransport(
        {
            "query": "ignored response echo",
            "results": [
                {
                    "title": "Job market report",
                    "url": "https://example.com/report",
                    "content": "Public market evidence.",
                    "raw_content": "must not enter the provider-neutral response",
                }
            ],
        }
    )
    provider = TavilyWebSearchProvider(
        settings=AppSettings(
            _env_file=None,
            web_search_enabled=True,
            web_search_max_results=3,
            web_search_timeout_seconds=7,
        ),
        secret_store=MemorySecretStore(),
        transport=transport,
    )

    assert isinstance(provider, WebSearchProvider)
    response = asyncio.run(
        provider.search(WebSearchRequest(query="  software hiring outlook  ", max_results=10))
    )

    url, api_key, payload, timeout = transport.calls[0]
    assert url == "https://api.tavily.com/search"
    assert payload == {"query": "software hiring outlook", "max_results": 3}
    assert api_key.get_secret_value() == "tavily-secret"
    assert timeout == 7
    assert response.model_dump(mode="json") == {
        "results": [
            {
                "title": "Job market report",
                "url": "https://example.com/report",
                "snippet": "Public market evidence.",
            }
        ]
    }
    assert "raw_content" not in response.model_dump_json()


def test_tavily_provider_rejects_missing_key_and_non_https_results() -> None:
    missing_provider = TavilyWebSearchProvider(
        settings=AppSettings(_env_file=None, web_search_enabled=True),
        secret_store=MemorySecretStore(None),
    )
    with pytest.raises(WebSearchMissingCredentialError) as missing:
        asyncio.run(missing_provider.search(WebSearchRequest(query="hiring")))

    malformed_provider = TavilyWebSearchProvider(
        settings=AppSettings(_env_file=None, web_search_enabled=True),
        secret_store=MemorySecretStore(),
        transport=RecordingTransport(
            {"results": [{"title": "Result", "url": "http://example.com", "content": "Snippet"}]}
        ),
    )
    with pytest.raises(WebSearchMalformedResponseError):
        asyncio.run(malformed_provider.search(WebSearchRequest(query="hiring")))

    assert "tavily-secret" not in str(missing.value)


@pytest.mark.parametrize(
    ("transport_error", "expected_error"),
    [
        (TavilyTransportError(status_code=401), WebSearchAuthenticationError),
        (TavilyTransportError(status_code=403), WebSearchAuthenticationError),
        (TavilyTransportError(status_code=429), WebSearchRateLimitError),
        (TavilyTransportError(status_code=None, is_timeout=True), WebSearchTimeoutError),
        (TavilyTransportError(status_code=503), WebSearchUnavailableError),
    ],
)
def test_tavily_provider_maps_public_safe_transport_errors(
    transport_error: TavilyTransportError,
    expected_error: type[Exception],
) -> None:
    provider = TavilyWebSearchProvider(
        settings=AppSettings(_env_file=None, web_search_enabled=True),
        secret_store=MemorySecretStore(),
        transport=RecordingTransport(transport_error),
    )

    with pytest.raises(expected_error) as error_info:
        asyncio.run(provider.search(WebSearchRequest(query="hiring")))

    assert "tavily-secret" not in str(error_info.value)
    assert "hiring" not in str(error_info.value)


def test_web_search_contract_bounds_requests_and_requires_https_base_url() -> None:
    with pytest.raises(ValidationError):
        WebSearchRequest(query="hiring", max_results=11)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, tavily_base_url="http://api.tavily.com")


def test_tavily_provider_refuses_calls_while_disabled() -> None:
    provider = TavilyWebSearchProvider(
        settings=AppSettings(_env_file=None, web_search_enabled=False),
        secret_store=MemorySecretStore(),
    )

    with pytest.raises(WebSearchUnavailableError, match="disabled"):
        asyncio.run(provider.search(WebSearchRequest(query="hiring")))
