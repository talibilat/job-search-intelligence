from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PipelineNextAction(StrEnum):
    """Deterministic next step a user can take to move the pipeline forward."""

    CONNECT_GMAIL = "connect_gmail"
    RUN_SYNC = "run_sync"
    CONTINUE_BACKFILL = "continue_backfill"
    WAIT_FOR_SYNC = "wait_for_sync"
    RUN_CLASSIFICATION = "run_classification"
    REVIEW_DASHBOARD = "review_dashboard"
    INSPECT_ERROR = "inspect_error"


class BackfillProgressState(StrEnum):
    """Public lifecycle state for the durable full metadata backfill."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStageCounts(BaseModel):
    """Deterministic per-stage counts computed from local SQLite only."""

    model_config = ConfigDict(frozen=True)

    raw_email_count: int = Field(ge=0)
    metadata_only_count: int = Field(ge=0)
    retained_body_count: int = Field(ge=0)
    filter_decision_count: int = Field(ge=0)
    filter_candidate_count: int = Field(ge=0)
    filter_rejected_count: int = Field(ge=0)
    classified_email_count: int = Field(ge=0)
    job_related_email_count: int = Field(ge=0)
    application_count: int = Field(ge=0)
    application_event_count: int = Field(ge=0)


class PipelineStatus(BaseModel):
    """Public-safe deterministic pipeline overview for the workflow page.

    Every number comes from local SQLite counts or persisted sync state.
    No LLM output and no email body content is involved.
    """

    model_config = ConfigDict(frozen=True)

    generated_at: datetime

    gmail_connected: bool
    account_display: str | None = None
    reauth_required: bool = False

    sync_running: bool
    sync_mode: str | None = None
    last_sync_started_at: datetime | None = None
    last_sync_finished_at: datetime | None = None

    backfill_state: BackfillProgressState
    backfill_pages_processed: int = Field(ge=0)
    backfill_messages_processed: int = Field(ge=0)
    backfill_complete: bool
    incremental_sync_ready: bool

    counts: PipelineStageCounts
    unclassified_retained_count: int = Field(ge=0)

    last_error: str | None = None

    next_action: PipelineNextAction
    next_action_reason: str = Field(min_length=1)
