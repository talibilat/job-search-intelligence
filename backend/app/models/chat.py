from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models._json import parse_json_column
from app.models.correction import JsonObjectList

type ChatMessageRole = Literal["user", "assistant", "tool", "system"]
type ChatRoute = Literal["quantitative", "content", "mixed"]
type ChatCitationSource = Literal["email", "application", "metric"]


class ChatMessageRecord(BaseModel):
    id: int
    conversation_id: str
    role: ChatMessageRole
    content: str
    citations_json: JsonObjectList
    tool_outputs_json: JsonObjectList
    created_at: datetime

    @field_validator("citations_json", "tool_outputs_json", mode="before")
    @classmethod
    def parse_json_lists(cls, value: object) -> object:
        return parse_json_column(value)


class ChatRequest(BaseModel):
    """One local grounded chat turn."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)
    retrieval_limit: int = Field(default=5, ge=1, le=20)

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("conversation_id")
    @classmethod
    def reject_blank_conversation_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("conversation_id must not be blank")
        return value


class ChatCitation(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation_id: str = Field(min_length=1)
    source: ChatCitationSource
    email_public_id: str | None = None
    application_id: str | None = None
    metric_template: str | None = None
    subject: str | None = None
    sent_at: datetime | None = None
    snippet: str | None = None


class ChatIncrement(BaseModel):
    """Ordered event in the non-streaming incremental response contract."""

    type: Literal["route", "tool", "answer"]
    content: str


class ChatResponse(BaseModel):
    conversation_id: str
    route: ChatRoute
    answer: str
    citations: list[ChatCitation]
    tool_outputs: JsonObjectList
    increments: list[ChatIncrement]


class ChatStreamEvent(BaseModel):
    """One server-sent event emitted while a grounded chat turn runs."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["route", "tool", "complete", "error"]
    conversation_id: str
    route: ChatRoute | None = None
    tool: Literal["structured_query", "semantic_search"] | None = None
    response: ChatResponse | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_event_payload(self) -> ChatStreamEvent:
        required_field = {
            "route": self.route,
            "tool": self.tool,
            "complete": self.response,
            "error": self.error_code,
        }[self.type]
        if required_field is None:
            raise ValueError(f"{self.type} stream event is missing its payload")
        if self.type == "error" and self.error_message is None:
            raise ValueError("error stream event is missing its public message")
        return self


class SemanticSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    email_public_id: str = Field(min_length=1)
    application_ids: tuple[str, ...] = ()
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1, repr=False)
    subject: str | None = None
    from_addr: str | None = None
    sent_at: datetime | None = None
    distance: float = Field(ge=0)
