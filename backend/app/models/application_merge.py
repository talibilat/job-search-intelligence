from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.records import ApplicationCorrectionRecord, ApplicationRecord


class ApplicationMergeRequest(BaseModel):
    source_application_id: str = Field(min_length=1)
    reason: str | None = None


class ApplicationMergeResponse(BaseModel):
    target_application_id: str
    source_application_id: str
    moved_event_count: int = Field(ge=0)
    application: ApplicationRecord
    correction: ApplicationCorrectionRecord
