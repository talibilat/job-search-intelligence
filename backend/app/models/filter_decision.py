from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EmailFilterDecisionOutcome(StrEnum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class EmailCandidateQueryStrategy(StrEnum):
    BROAD_JOB_SEARCH = "broad_job_search"


class EmailFilterDecisionRecord(BaseModel):
    """Stored heuristic filter decision for one raw email and strategy."""

    email_id: str = Field(min_length=1)
    strategy: EmailCandidateQueryStrategy
    outcome: EmailFilterDecisionOutcome
    reason: str = Field(min_length=1)
    decided_at: datetime
