from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models._json import parse_json_column

type ApplicationSource = Literal[
    "linkedin",
    "company_site",
    "indeed",
    "referral",
    "other",
]
type ApplicationStatus = Literal[
    "applied",
    "in_review",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
]
type WorkMode = Literal["remote", "hybrid", "onsite"]
type SponsorshipStatus = Literal["offered", "not_offered", "unknown"]


class ApplicationRecord(BaseModel):
    id: str
    company: str
    role_title: str
    source: ApplicationSource
    first_seen_at: datetime
    current_status: ApplicationStatus
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str | None
    location: str | None
    work_mode: WorkMode | None
    seniority: str | None
    sponsorship: SponsorshipStatus
    tech_stack: list[str]
    last_activity_at: datetime
    manual_lock: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("tech_stack", mode="before")
    @classmethod
    def parse_tech_stack(cls, value: object) -> object:
        return parse_json_column(value)

    @model_validator(mode="after")
    def validate_salary_range(self) -> Self:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            msg = "salary_min must be less than or equal to salary_max"
            raise ValueError(msg)
        return self
