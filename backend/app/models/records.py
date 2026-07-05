from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, field_validator

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


class RawEmailRecord(BaseModel):
    id: str
    thread_id: str | None
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    sent_at: datetime | None
    body_text: str | None
    body_retention_state: str
    labels: list[str]
    provider: str
    ingested_at: datetime

    @field_validator("labels", mode="before")
    @classmethod
    def parse_labels(cls, value: object) -> object:
        return parse_json_column(value)


class EmailSyncStateRecord(BaseModel):
    provider: str
    account_id: str
    sync_cursor: str
    cursor_issued_at: datetime
    updated_at: datetime


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
    email_id: str
    event_type: ApplicationEventType
    event_at: datetime
    extract_note: str | None


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
