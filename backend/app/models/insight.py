from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models._json import parse_json_column
from app.models.application import (
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from app.models.event import ApplicationEventType

type InsightType = Literal[
    "why_rejected",
    "recurring_feedback",
    "skill_gaps",
    "strongest_weakest_signals",
    "role_fit",
    "weekly_actions",
    "story",
]


class InsightRecord(BaseModel):
    id: int
    type: InsightType
    content: str
    inputs_hash: str
    is_stale: bool
    model: str
    generated_at: datetime


type InsightInputFactSource = Literal["applications", "application_events"]
type InsightInputFactName = Literal[
    "total_applications",
    "status_counts",
    "source_counts",
    "sponsorship_counts",
    "work_mode_counts",
    "event_type_counts",
    "rejected_skill_counts",
]
type InsightInputFactValue = int | float | str | bool | dict[str, int] | list[str] | None


class InsightInputFact(BaseModel):
    name: InsightInputFactName
    value: InsightInputFactValue
    source: InsightInputFactSource


class InsightInputEvidence(BaseModel):
    citation_id: str
    application_id: str
    company: str
    role_title: str
    application_status: ApplicationStatus
    source: ApplicationSource
    sponsorship: SponsorshipStatus
    work_mode: WorkMode | None
    tech_stack: list[str]
    event_id: str | None
    email_id: str | None
    event_type: ApplicationEventType | None
    event_at: datetime | None
    extract_note: str | None
    email_subject: str | None
    email_from: str | None
    email_sent_at: datetime | None
    email_body_text: str | None = Field(default=None, repr=False)

    @field_validator("tech_stack", mode="before")
    @classmethod
    def parse_tech_stack(cls, value: object) -> object:
        return parse_json_column(value)


class InsightInput(BaseModel):
    type: InsightType
    facts: list[InsightInputFact]
    evidence: list[InsightInputEvidence]
    source_fingerprint: str
    inputs_hash: str
