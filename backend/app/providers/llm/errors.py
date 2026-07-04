from __future__ import annotations


class LLMProviderError(RuntimeError):
    """Base error for public-safe LLM provider failures."""

    public_message: str

    def __init__(self, *, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when the configured LLM provider cannot be used."""


class LLMProviderRequestError(LLMProviderError):
    """Raised when a provider request fails before a valid response is returned."""


class LLMProviderResponseError(LLMProviderError):
    """Raised when a provider returns an invalid or unsupported response."""


class LLMProviderTimeoutError(LLMProviderError):
    """Raised when a provider request times out."""
