from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self, cast

from pydantic import BaseModel, Field, field_validator, model_validator

type ApplicationSource = Literal[
    "linkedin",
    "company_site",
    "indeed",
    "referral",
    "other",
]
type ApplicationStatus = Literal[
    "applied",
    "in_review",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
]
type WorkMode = Literal["remote", "hybrid", "onsite"]
type SponsorshipStatus = Literal["offered", "not_offered", "unknown"]
type ApplicationEventType = Literal[
    "applied",
    "response",
    "assessment",
    "interview_scheduled",
    "feedback",
    "rejection",
    "offer",
    "ghost_inferred",
]
type CorrectionType = Literal[
    "merge",
    "split",
    "status_edit",
    "event_edit",
    "reset_lock",
]
type InsightType = Literal[
    "why_rejected",
    "skill_gaps",
    "role_fit",
    "weekly_actions",
    "story",
]
type JsonObject = dict[str, object]
type JsonObjectList = list[JsonObject]


class RawEmailBodyRetentionState(StrEnum):
    """Explicit body retention state for raw email DTO boundaries."""

    METADATA_ONLY = "metadata_only"
    RETAINED = "retained"
    DEBUGGING = "debugging"


class EmailBackfillStatus(StrEnum):
    """Persisted lifecycle state for a full provider metadata backfill."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RawEmailRecord(BaseModel):
    """Raw email row DTO with explicit retained-body consistency checks."""

    id: str
    thread_id: str | None
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    sent_at: datetime | None
    body_text: str | None = Field(repr=False)
    body_retention_state: RawEmailBodyRetentionState
    labels: list[str]
    provider: str
    ingested_at: datetime

    @field_validator("labels", mode="before")
    @classmethod
    def parse_labels(cls, value: object) -> object:
        return parse_json_column(value)

    @model_validator(mode="after")
    def validate_body_retention_state(self) -> Self:
        if (
            self.body_retention_state is RawEmailBodyRetentionState.METADATA_ONLY
            and self.body_text is not None
        ):
            msg = "metadata-only raw emails cannot retain body_text"
            raise ValueError(msg)

        if self.has_retained_body and self.body_text is None:
            msg = "retained raw emails must include body_text"
            raise ValueError(msg)

        return self

    @property
    def has_retained_body(self) -> bool:
        """Return whether pipeline stages can read retained body text."""

        return self.body_retention_state in {
            RawEmailBodyRetentionState.RETAINED,
            RawEmailBodyRetentionState.DEBUGGING,
        }


class EmailSyncStateRecord(BaseModel):
    """Persisted opaque provider cursor for one email account."""

    provider: str
    account_id: str
    sync_cursor: str
    cursor_issued_at: datetime
    updated_at: datetime


class EmailBackfillStateRecord(BaseModel):
    """Persisted full-backfill cursor and page progress for one email account."""

    provider: str
    account_id: str
    status: EmailBackfillStatus
    next_page_token: str | None
    processed_page_count: int = Field(ge=0)
    processed_message_count: int = Field(ge=0)
    sync_cursor: str | None
    cursor_issued_at: datetime | None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    last_error: str | None

    @model_validator(mode="after")
    def validate_resume_state(self) -> Self:
        if (self.sync_cursor is None) != (self.cursor_issued_at is None):
            msg = "sync cursor and issued timestamp must be stored together"
            raise ValueError(msg)

        if self.status is EmailBackfillStatus.COMPLETED and self.next_page_token is not None:
            msg = "completed backfills cannot retain a next page token"
            raise ValueError(msg)

        if self.status is EmailBackfillStatus.COMPLETED and self.sync_cursor is None:
            msg = "completed backfills require a replacement sync cursor"
            raise ValueError(msg)

        if self.status is not EmailBackfillStatus.FAILED and self.last_error is not None:
            msg = "last_error is only valid for failed backfills"
            raise ValueError(msg)

        return self


class ApplicationRecord(BaseModel):
    id: str
    company: str
    role_title: str
    source: ApplicationSource
    first_seen_at: datetime
    current_status: ApplicationStatus
    salary_min: int | None
    salary_max: int | None
    currency: str | None
    location: str | None
    work_mode: WorkMode | None
    seniority: str | None
    sponsorship: SponsorshipStatus
    tech_stack: list[str]
    last_activity_at: datetime
    manual_lock: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("tech_stack", mode="before")
    @classmethod
    def parse_tech_stack(cls, value: object) -> object:
        return parse_json_column(value)


class ApplicationEventRecord(BaseModel):
    id: str
    application_id: str
    email_id: str | None
    event_type: ApplicationEventType
    event_at: datetime
    extract_note: str | None

    @model_validator(mode="after")
    def validate_email_id_for_event_type(self) -> Self:
        if self.event_type == "ghost_inferred" and self.email_id is not None:
            msg = "ghost-inferred events cannot reference email_id"
            raise ValueError(msg)
        if self.event_type != "ghost_inferred" and self.email_id is None:
            msg = "evidence-backed events require email_id"
            raise ValueError(msg)
        return self


class ApplicationCorrectionRecord(BaseModel):
    id: int
    application_id: str
    correction_type: CorrectionType
    before_json: JsonObject
    after_json: JsonObject
    reason: str | None
    created_at: datetime

    @field_validator("before_json", "after_json", mode="before")
    @classmethod
    def parse_json_objects(cls, value: object) -> object:
        return parse_json_column(value)


class InsightRecord(BaseModel):
    id: int
    type: InsightType
    content: str
    inputs_hash: str
    is_stale: bool
    model: str
    generated_at: datetime


class ChatMessageRecord(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    citations_json: JsonObjectList
    tool_outputs_json: JsonObjectList
    created_at: datetime

    @field_validator("citations_json", "tool_outputs_json", mode="before")
    @classmethod
    def parse_json_lists(cls, value: object) -> object:
        return parse_json_column(value)


def parse_json_column(value: object) -> object:
    if isinstance(value, str):
        return cast(object, json.loads(value))
    return value
