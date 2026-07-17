from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class InsightCitation(BaseModel):
    """Public-safe evidence pointer persisted alongside a cached insight.

    Carries only application and email metadata so insight cards can render
    clickable evidence chips without re-deriving the generation inputs.
    """

    citation_id: str
    application_id: str
    company: str
    role_title: str
    event_id: str | None = None
    email_id: str | None = None
    email_public_id: str | None = None
    event_type: ApplicationEventType | None = None
    event_at: datetime | None = None
    email_subject: str | None = None


class InsightRecord(BaseModel):
    id: int
    type: InsightType
    content: str
    inputs_hash: str
    is_stale: bool
    model: str
    generated_at: datetime
    citations: list[InsightCitation] = Field(default_factory=list)

    @field_validator("citations", mode="before")
    @classmethod
    def parse_citations(cls, value: object) -> object:
        parsed = parse_json_column(value)
        return [] if parsed is None else parsed


class InsightRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: InsightType
    max_evidence_items: int = Field(default=100, ge=1)


class InsightRegenerationCost(BaseModel):
    estimated_prompt_tokens: int = Field(ge=0)
    estimated_completion_tokens: int = Field(ge=0)
    estimated_total_tokens: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    actual_prompt_tokens: int | None = Field(default=None, ge=0)
    actual_completion_tokens: int | None = Field(default=None, ge=0)
    actual_total_tokens: int | None = Field(default=None, ge=0)
    actual_cost_usd: float | None = Field(default=None, ge=0)
    currency: str = "USD"
    cost_estimate_available: bool
    token_estimate_method: str = Field(min_length=1)


class InsightRegenerationEstimate(BaseModel):
    type: InsightType
    cost: InsightRegenerationCost


class InsightListResponse(BaseModel):
    insights: list[InsightRecord]
    regeneration_cost_estimates: list[InsightRegenerationEstimate] = Field(
        default_factory=list,
    )


class InsightRegenerateResponse(BaseModel):
    insight: InsightRecord
    cached: bool
    evidence_citation_ids: list[str]
    cost: InsightRegenerationCost


class InsightRoleOutcomeSummary(BaseModel):
    """Deterministic role-level outcome facts used to ground Q-44 synthesis."""

    role_title: str
    application_count: int
    win_count: int
    loss_count: int
    status_counts: dict[str, int]
    citation_ids: list[str]


type InsightInputFactSource = Literal["applications", "application_events"]
type InsightInputFactName = Literal[
    "total_applications",
    "status_counts",
    "source_counts",
    "sponsorship_counts",
    "work_mode_counts",
    "event_type_counts",
    "rejected_skill_counts",
    "role_outcome_summaries",
]
type InsightInputFactValue = (
    int | float | str | bool | dict[str, int] | list[str] | list[InsightRoleOutcomeSummary] | None
)


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
    email_public_id: str | None = Field(default=None, exclude=True)
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
