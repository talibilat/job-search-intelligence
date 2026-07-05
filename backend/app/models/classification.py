from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


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
