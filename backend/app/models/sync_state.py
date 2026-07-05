from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class EmailBackfillStatus(StrEnum):
    """Persisted lifecycle state for a full provider metadata backfill."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EmailSyncStateRecord(BaseModel):
    """Persisted provider cursor and in-progress page state for one account."""

    provider: str
    account_id: str
    sync_cursor: str | None = None
    cursor_issued_at: datetime | None = None
    in_progress_mode: str | None = None
    next_page_token: str | None = None
    updated_at: datetime


class EmailBackfillStateRecord(BaseModel):
    """Persisted full-backfill cursor and page progress for one email account."""

    provider: str
    account_id: str
    status: EmailBackfillStatus
    next_page_token: str | None
    processed_page_count: int = Field(ge=0)
    processed_message_count: int = Field(ge=0)
    sync_cursor: str | None
    cursor_issued_at: datetime | None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    last_error: str | None

    @model_validator(mode="after")
    def validate_resume_state(self) -> Self:
        if (self.sync_cursor is None) != (self.cursor_issued_at is None):
            msg = "sync cursor and issued timestamp must be stored together"
            raise ValueError(msg)

        if self.status is EmailBackfillStatus.COMPLETED and self.next_page_token is not None:
            msg = "completed backfills cannot retain a next page token"
            raise ValueError(msg)

        if self.status is EmailBackfillStatus.COMPLETED and self.sync_cursor is None:
            msg = "completed backfills require a replacement sync cursor"
            raise ValueError(msg)

        if self.status is not EmailBackfillStatus.FAILED and self.last_error is not None:
            msg = "last_error is only valid for failed backfills"
            raise ValueError(msg)

        return self
