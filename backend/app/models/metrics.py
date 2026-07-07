from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResponseSilenceMetric(BaseModel):
    question_id: Literal["Q-04"] = "Q-04"
    total_applications: int = Field(ge=0)
    human_response_count: int = Field(ge=0)
    silent_count: int = Field(ge=0)
