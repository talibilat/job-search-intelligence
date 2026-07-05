from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.models._json import parse_json_column

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
