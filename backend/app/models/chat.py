from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models._json import parse_json_column
from app.models.correction import JsonObjectList


class ChatMessageRecord(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    citations_json: JsonObjectList
    tool_outputs_json: JsonObjectList
    created_at: datetime

    @field_validator("citations_json", "tool_outputs_json", mode="before")
    @classmethod
    def parse_json_lists(cls, value: object) -> object:
        return parse_json_column(value)
