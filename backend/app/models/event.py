from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, model_validator

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
