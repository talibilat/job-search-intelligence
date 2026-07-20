from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class WebSearchRequest(BaseModel):
    """Provider-neutral web search request containing no local source content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, max_length=500, repr=False)
    max_results: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class WebSearchResult(BaseModel):
    """One public web result returned through the provider seam."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    url: HttpUrl
    snippet: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def require_https_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("web search result URLs must use HTTPS")
        return value


class WebSearchResponse(BaseModel):
    """Provider-neutral ordered web search results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: tuple[WebSearchResult, ...]
