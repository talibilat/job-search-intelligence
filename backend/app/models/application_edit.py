from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.application import ApplicationRecord, ApplicationStatus
from app.models.correction import ApplicationCorrectionRecord
from app.models.event import ApplicationEventRecord, ApplicationEventType

_EVENT_EDIT_FIELDS = frozenset({"event_type", "event_at", "email_id", "extract_note"})


class ApplicationStatusEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    current_status: ApplicationStatus
    reason: str | None = None


class ApplicationStatusEditResponse(BaseModel):
    application: ApplicationRecord
    correction: ApplicationCorrectionRecord


class ApplicationEventEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_type: ApplicationEventType | None = None
    event_at: datetime | None = None
    email_id: str | None = None
    extract_note: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def require_event_edit_field(self) -> Self:
        if not self.model_fields_set.intersection(_EVENT_EDIT_FIELDS):
            msg = "At least one event field must be edited."
            raise ValueError(msg)
        if "event_type" in self.model_fields_set and self.event_type is None:
            msg = "event_type cannot be null."
            raise ValueError(msg)
        if "event_at" in self.model_fields_set and self.event_at is None:
            msg = "event_at cannot be null."
            raise ValueError(msg)
        return self


class ApplicationEventEditResponse(BaseModel):
    application: ApplicationRecord
    event: ApplicationEventRecord
    correction: ApplicationCorrectionRecord
