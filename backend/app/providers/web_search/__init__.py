"""Provider-neutral web search contracts and Tavily adapter."""

from .errors import (
    WebSearchAuthenticationError,
    WebSearchMalformedResponseError,
    WebSearchMissingCredentialError,
    WebSearchProviderError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)
from .provider import WebSearchProvider
from .tavily import TavilyWebSearchProvider

__all__ = [
    "TavilyWebSearchProvider",
    "WebSearchAuthenticationError",
    "WebSearchMalformedResponseError",
    "WebSearchMissingCredentialError",
    "WebSearchProvider",
    "WebSearchProviderError",
    "WebSearchRateLimitError",
    "WebSearchTimeoutError",
    "WebSearchUnavailableError",
]
