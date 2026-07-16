from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.application import ApplicationStatus


class InterviewAttentionItem(BaseModel):
    application_id: str
    interview_event_id: str
    company: str
    role_title: str
    interview_at: datetime
    last_activity_at: datetime
    current_status: ApplicationStatus
    completed_at: datetime | None = None


class AttentionOverviewResponse(BaseModel):
    unique_interviewed_company_count: int = Field(ge=0)
    prepare: list[InterviewAttentionItem]
    interviewed: list[InterviewAttentionItem]
    follow_up: list[InterviewAttentionItem]


class InterviewTaskCompletionResponse(BaseModel):
    interview_event_id: str
    application_id: str
    completed_at: datetime
