from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ChatMessageRecord


class ChatRepository(BaseRepository[ChatMessageRecord]):
    """Repository seam for persisted chat messages."""

    def map_row(self, row: sqlite3.Row) -> ChatMessageRecord:
        return ChatMessageRecord.model_validate(row_to_dict(row))
