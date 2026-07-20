from __future__ import annotations

from app.models.web_search import WebSearchRequest, WebSearchResponse
from app.providers.web_search import WebSearchProvider


class WebSearchTool:
    """Execute one bounded public query without local private evidence."""

    def __init__(self, provider: WebSearchProvider) -> None:
        self._provider = provider

    async def run(self, request: WebSearchRequest) -> WebSearchResponse:
        return await self._provider.search(request)
