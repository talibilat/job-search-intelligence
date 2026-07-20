from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models._json import parse_json_column
from app.models.correction import JsonObjectList

type ChatMessageRole = Literal["user", "assistant", "tool", "system"]
type ChatRoute = Literal["conversation", "quantitative", "content", "web", "mixed"]
type ChatCitationSource = Literal["email", "application", "metric", "web"]
type ChatAnswerKind = Literal["conversation", "grounded", "refusal"]


class RetrievalPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["semantic", "latest_company_email", "exhaustive_mentions"]
    query: str = Field(min_length=1, max_length=4000)
    company: str | None = Field(default=None, min_length=1, max_length=300)
    term: str | None = Field(default=None, min_length=1, max_length=300)
    category: Literal["rejection"] | None = None
    company_results: bool = False

    @model_validator(mode="after")
    def validate_mode_fields(self) -> Self:
        if self.mode == "latest_company_email" and self.company is None:
            raise ValueError("latest_company_email requires company")
        if self.mode == "exhaustive_mentions" and self.term is None:
            raise ValueError("exhaustive_mentions requires term")
        if self.mode != "exhaustive_mentions" and (
            self.term is not None or self.category is not None or self.company_results
        ):
            raise ValueError("mention fields require exhaustive_mentions")
        return self


class ApplicationFollowUpState(BaseModel):
    model_config = ConfigDict(frozen=True)

    application_id: str
    latest_event_at: datetime
    latest_event_type: str
    latest_direction: Literal["inbound", "outbound", "unknown"]
    has_future_interview: bool


class ChatFollowUpPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageRecord(BaseModel):
    id: int
    conversation_id: str
    turn_id: str | None = Field(default=None, min_length=1, max_length=100)
    role: ChatMessageRole
    route: ChatRoute | None = None
    answer_kind: ChatAnswerKind | None = None
    content: str
    citations_json: JsonObjectList
    tool_outputs_json: JsonObjectList
    follow_up_prompts_json: JsonObjectList = Field(default_factory=list)
    created_at: datetime

    @field_validator("citations_json", "tool_outputs_json", "follow_up_prompts_json", mode="before")
    @classmethod
    def parse_json_lists(cls, value: object) -> object:
        return parse_json_column(value)


class ChatRequest(BaseModel):
    """One local grounded chat turn."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)
    retrieval_limit: int = Field(default=5, ge=1, le=20)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("turn_id")
    @classmethod
    def reject_blank_turn_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("turn_id must not be blank")
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
    company: str | None = Field(default=None, exclude_if=lambda value: value is None)
    role_title: str | None = Field(default=None, exclude_if=lambda value: value is None)
    current_status: str | None = Field(default=None, exclude_if=lambda value: value is None)
    first_seen_at: datetime | None = Field(default=None, exclude_if=lambda value: value is None)
    web_title: str | None = Field(default=None, exclude_if=lambda value: value is None)
    web_url: str | None = Field(default=None, exclude_if=lambda value: value is None)
    web_domain: str | None = Field(default=None, exclude_if=lambda value: value is None)


class ChatIncrement(BaseModel):
    """Ordered event in the non-streaming incremental response contract."""

    type: Literal["route", "tool", "answer"]
    content: str


class ChatResponse(BaseModel):
    conversation_id: str
    route: ChatRoute
    answer: str
    answer_kind: ChatAnswerKind = "grounded"
    citations: list[ChatCitation]
    tool_outputs: JsonObjectList
    increments: list[ChatIncrement]
    follow_up_prompts: list[ChatFollowUpPrompt] = Field(default_factory=list)


class ChatStreamEvent(BaseModel):
    """One server-sent event emitted while a grounded chat turn runs."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["route", "tool", "answer_delta", "complete", "error"]
    conversation_id: str
    route: ChatRoute | None = None
    tool: Literal["structured_query", "semantic_search", "cached_insight", "web_search"] | None = (
        None
    )
    answer_delta: str | None = None
    response: ChatResponse | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_event_payload(self) -> ChatStreamEvent:
        required_field = {
            "route": self.route,
            "tool": self.tool,
            "answer_delta": self.answer_delta,
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
    company: str | None = None
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1, repr=False)
    subject: str | None = None
    from_addr: str | None = None
    sent_at: datetime | None = None
    distance: float = Field(ge=0)
