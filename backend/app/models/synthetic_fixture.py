from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import EmailProviderName
from app.models.records import RawEmailBodyRetentionState

SyntheticBodyRetentionState = RawEmailBodyRetentionState


class SyntheticJobEmailCategory(StrEnum):
    APPLICATION_CONFIRMATION = "application_confirmation"
    REJECTION = "rejection"
    INTERVIEW_INVITE = "interview_invite"
    RECRUITER_OUTREACH = "recruiter_outreach"
    OFFER = "offer"
    ASSESSMENT = "assessment"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class SyntheticApplicationSource(StrEnum):
    LINKEDIN = "linkedin"
    COMPANY_SITE = "company_site"
    INDEED = "indeed"
    REFERRAL = "referral"
    OTHER = "other"


class SyntheticApplicationStatus(StrEnum):
    APPLIED = "applied"
    IN_REVIEW = "in_review"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"
    WITHDRAWN = "withdrawn"


class SyntheticWorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class SyntheticSponsorship(StrEnum):
    OFFERED = "offered"
    NOT_OFFERED = "not_offered"
    UNKNOWN = "unknown"


class SyntheticEventType(StrEnum):
    APPLIED = "applied"
    RESPONSE = "response"
    ASSESSMENT = "assessment"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    FEEDBACK = "feedback"
    REJECTION = "rejection"
    OFFER = "offer"
    GHOST_INFERRED = "ghost_inferred"


class SyntheticRawEmail(BaseModel):
    """Private-data-free raw email row for synthetic fixtures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    provider: EmailProviderName
    thread_id: str | None = Field(default=None, min_length=1)
    from_addr: str | None = Field(default=None, min_length=1)
    to_addr: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, min_length=1)
    sent_at: datetime | None = None
    body_text: str | None = Field(default=None, repr=False)
    body_retention_state: SyntheticBodyRetentionState = SyntheticBodyRetentionState.METADATA_ONLY
    labels: tuple[str, ...] = ()
    ingested_at: datetime


class SyntheticEmailClassification(BaseModel):
    """Synthetic `email_classifications` row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email_id: str = Field(min_length=1)
    is_job_related: bool
    category: SyntheticJobEmailCategory
    confidence: float = Field(ge=0, le=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    classified_at: datetime


class SyntheticApplication(BaseModel):
    """Synthetic `applications` row that metrics and aggregation tests can share."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    source: SyntheticApplicationSource = SyntheticApplicationSource.OTHER
    first_seen_at: datetime
    current_status: SyntheticApplicationStatus
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    location: str | None = Field(default=None, min_length=1)
    work_mode: SyntheticWorkMode | None = None
    seniority: str | None = Field(default=None, min_length=1)
    sponsorship: SyntheticSponsorship = SyntheticSponsorship.UNKNOWN
    tech_stack: tuple[str, ...] = ()
    last_activity_at: datetime
    manual_lock: bool = False
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_salary_range(self) -> Self:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            msg = "salary_min must be less than or equal to salary_max"
            raise ValueError(msg)
        return self


class SyntheticApplicationEvent(BaseModel):
    """Synthetic `application_events` row."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    email_id: str = Field(min_length=1)
    event_type: SyntheticEventType
    event_at: datetime
    extract_note: str | None = Field(default=None, min_length=1)


class SyntheticFixtureFile(BaseModel):
    """Versioned synthetic fixture contract shared by tests and loaders."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"]
    fixture_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    contains_private_data: Literal[False]
    emails: tuple[SyntheticRawEmail, ...] = ()
    classifications: tuple[SyntheticEmailClassification, ...] = ()
    applications: tuple[SyntheticApplication, ...] = ()
    events: tuple[SyntheticApplicationEvent, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        email_ids = [email.id for email in self.emails]
        classification_email_ids = [
            classification.email_id for classification in self.classifications
        ]
        application_ids = [application.id for application in self.applications]
        event_ids = [event.id for event in self.events]

        self._reject_duplicates("email ids", email_ids)
        self._reject_duplicates("classification email ids", classification_email_ids)
        self._reject_duplicates("application ids", application_ids)
        self._reject_duplicates("event ids", event_ids)

        known_email_ids = set(email_ids)
        unknown_classification_email_ids = set(classification_email_ids) - known_email_ids
        unknown_event_email_ids = {event.email_id for event in self.events} - known_email_ids
        if unknown_classification_email_ids or unknown_event_email_ids:
            unknown_email_ids = unknown_classification_email_ids | unknown_event_email_ids
            msg = f"unknown email ids: {_format_ids(unknown_email_ids)}"
            raise ValueError(msg)

        known_application_ids = set(application_ids)
        unknown_application_ids = {
            event.application_id for event in self.events
        } - known_application_ids
        if unknown_application_ids:
            msg = f"unknown application ids: {_format_ids(unknown_application_ids)}"
            raise ValueError(msg)

        return self

    @staticmethod
    def _reject_duplicates(label: str, values: Iterable[str]) -> None:
        duplicates = _find_duplicates(values)
        if duplicates:
            msg = f"duplicate {label}: {_format_ids(duplicates)}"
            raise ValueError(msg)


class SyntheticFixtureLoadResult(BaseModel):
    """Summary of a synthetic fixture load into SQLite."""

    model_config = ConfigDict(frozen=True)

    fixture_id: str = Field(min_length=1)
    email_count: int = Field(ge=0)
    classification_count: int = Field(ge=0)
    application_count: int = Field(ge=0)
    event_count: int = Field(ge=0)


def _find_duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _format_ids(values: Iterable[str]) -> str:
    return ", ".join(sorted(values))
