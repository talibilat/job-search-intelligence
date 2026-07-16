from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.models.application import ApplicationStatus

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

RESPONSE_LIKE_APPLICATION_EVENT_TYPES: tuple[ApplicationEventType, ...] = (
    "assessment",
    "feedback",
    "interview_scheduled",
    "offer",
    "rejection",
    "response",
)


class ApplicationEventRecord(BaseModel):
    id: str
    application_id: str
    email_id: str | None
    event_type: ApplicationEventType
    event_at: datetime
    extract_note: str | None
    extracted_status: ApplicationStatus | None = None
    email_sent_at: datetime | None = None
    classification_classified_at: datetime | None = None

    @model_validator(mode="after")
    def validate_email_id_for_event_type(self) -> Self:
        if self.event_type == "ghost_inferred" and self.email_id is not None:
            msg = "ghost-inferred events cannot reference email_id"
            raise ValueError(msg)
        if self.event_type != "ghost_inferred" and self.email_id is None:
            msg = "evidence-backed events require email_id"
            raise ValueError(msg)
        return self


class ApplicationEventTimelineRecord(ApplicationEventRecord):
    """Application event enriched with source-email metadata for timeline UIs.

    Exposes only email metadata (subject), never body-derived content.
    """

    email_subject: str | None = None
    email_public_id: str | None = None
    classification_confidence: float | None = Field(default=None, ge=0, le=1)


class RecentApplicationEventRecord(BaseModel):
    """One cross-application timeline event for the recent-activity feed."""

    event_id: str
    application_id: str
    company: str
    role_title: str
    current_status: ApplicationStatus
    event_type: ApplicationEventType
    event_at: datetime
    email_id: str | None = None
    email_subject: str | None = None
