from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models._json import parse_json_column
from app.models.application import ApplicationRecord, ApplicationSource
from app.models.event import ApplicationEventRecord

type CorrectionType = Literal[
    "merge",
    "split",
    "status_edit",
    "event_edit",
    "reset_lock",
]
type JsonObject = dict[str, object]
type JsonObjectList = list[JsonObject]


class ApplicationCorrectionRecord(BaseModel):
    id: int
    application_id: str
    correction_type: CorrectionType
    before_json: JsonObject
    after_json: JsonObject
    reason: str | None
    created_at: datetime

    @field_validator("before_json", "after_json", mode="before")
    @classmethod
    def parse_json_objects(cls, value: object) -> object:
        return parse_json_column(value)


class ApplicationSplitNewApplication(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    source: ApplicationSource = "other"


class ApplicationSplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_ids: list[str] = Field(min_length=1)
    new_application: ApplicationSplitNewApplication
    reason: str | None = None

    @field_validator("event_ids")
    @classmethod
    def validate_event_ids(cls, value: list[str]) -> list[str]:
        normalized = [event_id.strip() for event_id in value]
        if any(not event_id for event_id in normalized):
            msg = "event_ids cannot contain blank values"
            raise ValueError(msg)
        if len(set(normalized)) != len(normalized):
            msg = "event_ids must be unique"
            raise ValueError(msg)
        return normalized


class ApplicationSplitResponse(BaseModel):
    source_application: ApplicationRecord
    new_application: ApplicationRecord
    moved_events: list[ApplicationEventRecord]
    correction: ApplicationCorrectionRecord
