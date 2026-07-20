from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.web_search import WebSearchRequest, WebSearchResponse


@runtime_checkable
class WebSearchProvider(Protocol):
    """Strategy seam for query-only web search providers."""

    provider_name: str

    async def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Search the public web without sending local application or email content."""
        ...
