from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.chat import ChatAnswerKind, ChatMessageRecord, ChatMessageRole, ChatRoute
from app.models.correction import JsonObjectList

CHAT_MESSAGE_COLUMNS = """
    id,
    conversation_id,
    turn_id,
    role,
    route,
    answer_kind,
    content,
    citations_json,
    tool_outputs_json,
    follow_up_prompts_json,
    created_at
"""


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
                {CHAT_MESSAGE_COLUMNS}
            FROM (
                SELECT
                    {CHAT_MESSAGE_COLUMNS}
                FROM chat_messages
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            ) AS recent_messages
            ORDER BY created_at ASC, id ASC
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
        citations: JsonObjectList,
        tool_outputs: JsonObjectList,
        created_at: datetime,
        turn_id: str | None = None,
        route: ChatRoute | None = None,
        answer_kind: ChatAnswerKind | None = None,
        follow_up_prompts: JsonObjectList | None = None,
    ) -> ChatMessageRecord:
        cursor = self.execute(
            """
            INSERT INTO chat_messages (
                conversation_id,
                turn_id,
                role,
                route,
                answer_kind,
                content,
                citations_json,
                tool_outputs_json,
                follow_up_prompts_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                turn_id,
                role,
                route,
                answer_kind,
                content,
                json.dumps(citations, separators=(",", ":")),
                json.dumps(tool_outputs, separators=(",", ":")),
                json.dumps(follow_up_prompts or [], separators=(",", ":")),
                created_at.isoformat(),
            ),
        )
        row = self.execute(
            """
            SELECT
                id,
                conversation_id,
                turn_id,
                role,
                route,
                answer_kind,
                content,
                citations_json,
                tool_outputs_json,
                follow_up_prompts_json,
                created_at
            FROM chat_messages WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("persisted chat message could not be read")
        return self.map_row(row)

    def get_completed_assistant_turn(
        self,
        *,
        turn_id: str,
        conversation_id: str | None = None,
    ) -> ChatMessageRecord | None:
        conversation_filter = ""
        parameters: tuple[object, ...] = (turn_id,)
        if conversation_id is not None:
            conversation_filter = "AND conversation_id = ?"
            parameters = (turn_id, conversation_id)

        row = self.execute(
            f"""
            SELECT
                {CHAT_MESSAGE_COLUMNS}
            FROM chat_messages
            WHERE turn_id = ?
              AND role = 'assistant'
              AND route IS NOT NULL
              {conversation_filter}
            """,
            parameters,
        ).fetchone()
        if row is None:
            return None
        return self.map_row(row)

    def get_user_turn(self, *, turn_id: str) -> ChatMessageRecord | None:
        row = self.execute(
            f"""
            SELECT {CHAT_MESSAGE_COLUMNS}
            FROM chat_messages
            WHERE turn_id = ? AND role = 'user'
            """,
            (turn_id,),
        ).fetchone()
        return self.map_row(row) if row is not None else None

    def map_row(self, row: sqlite3.Row) -> ChatMessageRecord:
        return ChatMessageRecord.model_validate(row_to_dict(row))
