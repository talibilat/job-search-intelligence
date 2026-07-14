from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.config import ClassificationMode, LLMProviderName


class ProcessingRunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProcessingRunRequest(BaseModel):
    """Explicit user-controlled bound for one processing run."""

    model_config = ConfigDict(extra="forbid")

    max_candidates: int | None = Field(default=None, ge=1, le=10_000)


class ProcessingStatus(BaseModel):
    """Public-safe status and accounting for current or latest processing work."""

    model_config = ConfigDict(frozen=True)

    state: ProcessingRunState
    run_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    pending_candidate_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    candidate_limit: int = Field(ge=1)
    processed_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    malformed_count: int = Field(ge=0)
    skipped_not_job_count: int = Field(ge=0)
    applications_upserted: int = Field(ge=0)
    events_upserted: int = Field(ge=0)
    ghost_updates: int = Field(ge=0)
    ghost_retractions: int = Field(ge=0)
    manual_conflict_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode
    limit_reached: bool = False
    last_error: str | None = None


class ProcessingRunResult(ProcessingStatus):
    """Completed processing result returned by the explicit run endpoint."""

    state: ProcessingRunState = ProcessingRunState.SUCCEEDED
