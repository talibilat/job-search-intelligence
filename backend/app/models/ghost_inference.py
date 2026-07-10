from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GhostInferenceRunApiRequest(BaseModel):
    """Empty request contract for the no-payload ghost-inference run endpoint."""

    model_config = ConfigDict(extra="forbid")


class GhostInferenceRunResponse(BaseModel):
    """Public result for one ghost-inference run."""

    model_config = ConfigDict(frozen=True)

    evaluated_at: datetime
    threshold_days: int = Field(ge=1)
    applications_ghosted: int = Field(ge=0)
    ghosted_application_ids: list[str]
    ghost_retraction_count: int = Field(ge=0)
    retracted_application_ids: list[str]
    manual_conflict_count: int = Field(ge=0)
    manual_conflict_application_ids: list[str]
