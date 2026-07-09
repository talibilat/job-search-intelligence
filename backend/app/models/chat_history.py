from __future__ import annotations

from pydantic import BaseModel

from app.models.chat import ChatMessageRecord


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageRecord]
