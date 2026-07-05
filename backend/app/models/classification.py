from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.application import ApplicationStatus, SponsorshipStatus, WorkMode
from app.models.event import ApplicationEventType

NonEmptyString = Annotated[str, Field(min_length=1)]


class JobEmailCategory(StrEnum):
    APPLICATION_CONFIRMATION = "application_confirmation"
    REJECTION = "rejection"
    INTERVIEW_INVITE = "interview_invite"
    RECRUITER_OUTREACH = "recruiter_outreach"
    OFFER = "offer"
    ASSESSMENT = "assessment"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class EmailClassificationRecord(BaseModel):
    """Stored classification result for one raw email."""

    email_id: str = Field(min_length=1)
    is_job_related: bool
    category: JobEmailCategory
    confidence: float = Field(ge=0, le=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    classified_at: datetime


class ClassificationRunRecord(BaseModel):
    """Per-run classification token usage and estimated cost."""

    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    candidate_count: int = Field(ge=0)
    classified_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=Decimal("0"))

    @model_validator(mode="after")
    def validate_accounting_totals(self) -> Self:
        if self.classified_count > self.candidate_count:
            msg = "classified_count cannot exceed candidate_count"
            raise ValueError(msg)

        counted_tokens = self.prompt_tokens + self.completion_tokens
        if self.total_tokens < counted_tokens:
            msg = "total_tokens cannot be less than prompt_tokens plus completion_tokens"
            raise ValueError(msg)

        return self


class ClassificationPromptOutput(BaseModel):
    """Structured LLM output expected from the classification prompt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_job_related: bool
    category: JobEmailCategory
    confidence: float = Field(ge=0, le=1)
    company: str | None = Field(min_length=1)
    role_title: str | None = Field(min_length=1)
    application_status: ApplicationStatus | None
    event_type: ApplicationEventType | None
    event_at: datetime | None
    salary_min: int | None = Field(ge=0)
    salary_max: int | None = Field(ge=0)
    currency: str | None = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    location: str | None = Field(min_length=1)
    work_mode: WorkMode | None
    seniority: str | None = Field(min_length=1)
    sponsorship: SponsorshipStatus
    tech_stack: tuple[NonEmptyString, ...]
    rejection_reason: str | None = Field(min_length=1)

    @model_validator(mode="after")
    def validate_extraction_shape(self) -> Self:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            msg = "salary_min must be less than or equal to salary_max"
            raise ValueError(msg)

        if self.is_job_related:
            return self

        if self.category is not JobEmailCategory.OTHER:
            msg = "non-job-related outputs must use category other"
            raise ValueError(msg)

        extracted_values = (
            self.company,
            self.role_title,
            self.application_status,
            self.event_type,
            self.event_at,
            self.salary_min,
            self.salary_max,
            self.currency,
            self.location,
            self.work_mode,
            self.seniority,
            self.rejection_reason,
        )
        if any(value is not None for value in extracted_values) or self.tech_stack:
            msg = "non-job-related outputs cannot include extracted application data"
            raise ValueError(msg)

        return self
