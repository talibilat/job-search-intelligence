from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LLMMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMResponseFormat(StrEnum):
    TEXT = "text"
    JSON_OBJECT = "json_object"


class LLMFinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    UNKNOWN = "unknown"


class LLMMessage(BaseModel):
    """One provider-neutral chat message."""

    model_config = ConfigDict(frozen=True)

    role: LLMMessageRole
    content: str = Field(min_length=1)


class LLMGenerationOptions(BaseModel):
    """Provider-neutral generation controls."""

    model_config = ConfigDict(frozen=True)

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1)


class LLMGenerationRequest(BaseModel):
    """Provider-neutral request for text or JSON-object generation."""

    model_config = ConfigDict(frozen=True)

    messages: tuple[LLMMessage, ...] = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    response_format: LLMResponseFormat = LLMResponseFormat.TEXT
    options: LLMGenerationOptions = Field(default_factory=LLMGenerationOptions)


class LLMTokenUsage(BaseModel):
    """Provider-neutral token accounting returned by a provider when available."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class LLMGenerationResponse(BaseModel):
    """Provider-neutral generated content and metadata."""

    model_config = ConfigDict(frozen=True)

    content: str
    model: str = Field(min_length=1)
    finish_reason: LLMFinishReason = LLMFinishReason.UNKNOWN
    usage: LLMTokenUsage | None = None
