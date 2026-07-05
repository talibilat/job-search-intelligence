from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


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
