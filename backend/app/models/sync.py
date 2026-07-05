from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import EmailProviderName


class SyncJobPhase(StrEnum):
    """Public-safe phase for the current local email sync job."""

    IDLE = "idle"
    QUEUED = "queued"
    METADATA_SYNC = "metadata_sync"
    BODY_RETENTION = "body_retention"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncJobCounts(BaseModel):
    """Deterministic counters reported by sync status."""

    model_config = ConfigDict(frozen=True)

    metadata_pages: int = Field(default=0, ge=0)
    metadata_messages: int = Field(default=0, ge=0)
    raw_emails_written: int = Field(default=0, ge=0)
    retained_bodies: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)


class SyncJobError(BaseModel):
    """Public-safe sync error summary without provider payloads or email content."""

    model_config = ConfigDict(frozen=True)

    message: str = Field(min_length=1)
    occurred_at: datetime


class SyncJobStatus(BaseModel):
    """Current sync job state for the `/sync/status` API boundary."""

    model_config = ConfigDict(frozen=True)

    phase: SyncJobPhase
    provider: EmailProviderName | None = None
    account_id: str | None = Field(default=None, min_length=1)
    counts: SyncJobCounts
    errors: tuple[SyncJobError, ...] = ()
    started_at: datetime | None = None
    updated_at: datetime
    completed_at: datetime | None = None
    progress: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> Self:
        if self.started_at is None:
            if self.completed_at is not None:
                msg = "completed_at requires started_at"
                raise ValueError(msg)
            return self

        if self.updated_at < self.started_at:
            msg = "updated_at cannot be before started_at"
            raise ValueError(msg)
        if self.completed_at is not None and self.completed_at < self.started_at:
            msg = "completed_at cannot be before started_at"
            raise ValueError(msg)
        return self
