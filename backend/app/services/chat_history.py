from __future__ import annotations

from app.db.repositories import ChatRepository
from app.models.chat import ChatMessageRecord


class ChatHistoryService:
    """Read persisted local chat history for the Phase 5 chat UI."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._chat_repository = chat_repository

    def list_messages(
        self,
        *,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[ChatMessageRecord]:
        return list(
            self._chat_repository.list_messages(
                conversation_id=conversation_id,
                limit=limit,
            )
        )
