from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EmailFilterDecisionOutcome(StrEnum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class EmailFilterDecisionRecord(BaseModel):
    """Stored heuristic filter decision for one raw email and strategy."""

    email_id: str = Field(min_length=1)
    strategy: str = Field(min_length=1)
    outcome: EmailFilterDecisionOutcome
    reason: str = Field(min_length=1)
    decided_at: datetime
