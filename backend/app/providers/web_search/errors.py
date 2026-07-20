from __future__ import annotations


class WebSearchProviderError(RuntimeError):
    """Base error for public-safe web search provider failures."""

    public_message: str

    def __init__(self, *, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class WebSearchMissingCredentialError(WebSearchProviderError):
    """Raised when the configured web search credential is absent."""


class WebSearchAuthenticationError(WebSearchProviderError):
    """Raised when the provider rejects its configured credential."""


class WebSearchRateLimitError(WebSearchProviderError):
    """Raised when the provider rate limit has been reached."""


class WebSearchTimeoutError(WebSearchProviderError):
    """Raised when a provider request times out."""


class WebSearchMalformedResponseError(WebSearchProviderError):
    """Raised when a provider returns an invalid response."""


class WebSearchUnavailableError(WebSearchProviderError):
    """Raised when web search or credential storage is unavailable."""
