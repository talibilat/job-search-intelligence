from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

type InsightType = Literal[
    "why_rejected",
    "skill_gaps",
    "role_fit",
    "weekly_actions",
    "story",
]


class InsightRecord(BaseModel):
    id: int
    type: InsightType
    content: str
    inputs_hash: str
    is_stale: bool
    model: str
    generated_at: datetime
