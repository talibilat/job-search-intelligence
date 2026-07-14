from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ChatMessageRecord, ChatMessageRole


class ChatRepository(BaseRepository[ChatMessageRecord]):
    """Repository seam for persisted chat messages."""

    def list_messages(
        self,
        *,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> tuple[ChatMessageRecord, ...]:
        if limit < 1:
            msg = "limit must be at least 1"
            raise ValueError(msg)

        where_clause = ""
        parameters: tuple[object, ...] = (limit,)
        if conversation_id is not None:
            where_clause = "WHERE conversation_id = ?"
            parameters = (conversation_id, limit)

        rows = self.execute(
            f"""
            SELECT
                id,
                conversation_id,
                role,
                content,
                citations_json,
                tool_outputs_json,
                created_at
            FROM chat_messages
            {where_clause}
            ORDER BY conversation_id ASC, created_at ASC, id ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return tuple(self.map_row(row) for row in rows)

    def add_message(
        self,
        *,
        conversation_id: str,
        role: ChatMessageRole,
        content: str,
        citations: list[dict[str, object]],
        tool_outputs: list[dict[str, object]],
        created_at: datetime,
    ) -> ChatMessageRecord:
        cursor = self.execute(
            """
            INSERT INTO chat_messages (
                conversation_id, role, content, citations_json, tool_outputs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                json.dumps(citations, separators=(",", ":")),
                json.dumps(tool_outputs, separators=(",", ":")),
                created_at.isoformat(),
            ),
        )
        row = self.execute(
            """
            SELECT id, conversation_id, role, content, citations_json, tool_outputs_json, created_at
            FROM chat_messages WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("persisted chat message could not be read")
        return self.map_row(row)

    def map_row(self, row: sqlite3.Row) -> ChatMessageRecord:
        return ChatMessageRecord.model_validate(row_to_dict(row))
