from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import (
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
)


@runtime_checkable
class LLMProvider(Protocol):
    """Strategy seam for provider-specific LLM generation adapters."""

    provider_name: str

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        """Generate provider-neutral content for a typed request."""
        ...

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        """Verify the configured provider models can be used before a run starts."""
        ...
