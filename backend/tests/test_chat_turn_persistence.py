from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.db.repositories import ChatRepository
from app.models.chat import ChatRequest
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
REVISION = "20260718_0248"


def test_migration_preserves_legacy_chat_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = alembic_config(database_path)
    command.upgrade(config, "20260715_0240")
    with sqlite3.connect(database_path) as connection:
        insert_message(connection, conversation_id="legacy", role="assistant")
        connection.commit()

    command.upgrade(config, REVISION)

    with sqlite3.connect(database_path) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(chat_messages)")}
        row = connection.execute(
            "SELECT turn_id, route, answer_kind, content FROM chat_messages "
            "WHERE conversation_id = ?",
            ("legacy",),
        ).fetchone()
        indexes = {str(row[1]) for row in connection.execute("PRAGMA index_list(chat_messages)")}

    assert {"turn_id", "route", "answer_kind"} <= columns
    assert row == (None, None, None, "message")
    assert {
        "uq_chat_messages_user_turn_id",
        "uq_chat_messages_assistant_turn_id",
    } <= indexes


def test_partial_indexes_prevent_duplicate_turn_endpoints_but_allow_tools(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_message(connection, conversation_id="conversation-1", role="user", turn_id="turn-1")
        insert_message(
            connection,
            conversation_id="conversation-1",
            role="assistant",
            turn_id="turn-1",
            route="mixed",
            answer_kind="grounded",
        )
        insert_message(connection, conversation_id="conversation-1", role="tool", turn_id="turn-1")
        insert_message(connection, conversation_id="conversation-1", role="tool", turn_id="turn-1")

        with pytest.raises(sqlite3.IntegrityError):
            insert_message(
                connection,
                conversation_id="conversation-2",
                role="user",
                turn_id="turn-1",
            )
        with pytest.raises(sqlite3.IntegrityError):
            insert_message(
                connection,
                conversation_id="conversation-2",
                role="assistant",
                turn_id="turn-1",
                route="content",
            )

        tool_count = connection.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE role = 'tool' AND turn_id = ?",
            ("turn-1",),
        ).fetchone()

    assert tool_count == (2,)


def test_repository_returns_completed_assistant_turn_with_response_data(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = ChatRepository(connection)
        repository.add_message(
            conversation_id="conversation-1",
            turn_id="turn-1",
            role="assistant",
            route="mixed",
            answer_kind="grounded",
            content="One application is waiting on a response.",
            citations=[{"citation_id": "metric:live_applications"}],
            tool_outputs=[{"tool": "structured_query", "count": 1}],
            created_at=CREATED_AT,
        )

        scoped = repository.get_completed_assistant_turn(
            turn_id="turn-1",
            conversation_id="conversation-1",
        )
        global_result = repository.get_completed_assistant_turn(turn_id="turn-1")
        wrong_conversation = repository.get_completed_assistant_turn(
            turn_id="turn-1",
            conversation_id="conversation-2",
        )

    assert scoped is not None
    assert scoped == global_result
    assert scoped.turn_id == "turn-1"
    assert scoped.route == "mixed"
    assert scoped.answer_kind == "grounded"
    assert scoped.content == "One application is waiting on a response."
    assert scoped.citations_json == [{"citation_id": "metric:live_applications"}]
    assert scoped.tool_outputs_json == [{"tool": "structured_query", "count": 1}]
    assert wrong_conversation is None


def test_repository_does_not_return_an_assistant_turn_without_a_route(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = ChatRepository(connection)
        repository.add_message(
            conversation_id="conversation-1",
            turn_id="turn-incomplete",
            role="assistant",
            content="Not completed",
            citations=[],
            tool_outputs=[],
            created_at=CREATED_AT,
        )

        result = repository.get_completed_assistant_turn(turn_id="turn-incomplete")

    assert result is None


@pytest.mark.parametrize("turn_id", ("", "   ", "x" * 101))
def test_chat_request_requires_bounded_nonblank_turn_id(turn_id: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(turn_id=turn_id, message="How many applications?")


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    command.upgrade(alembic_config(database_path), REVISION)
    return database_path


def alembic_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    return config


def insert_message(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    role: str,
    turn_id: str | None = None,
    route: str | None = None,
    answer_kind: str | None = None,
) -> None:
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(chat_messages)")}
    if "turn_id" not in columns:
        connection.execute(
            """
            INSERT INTO chat_messages (
                conversation_id, role, content, citations_json, tool_outputs_json, created_at
            ) VALUES (?, ?, ?, '[]', '[]', ?)
            """,
            (conversation_id, role, "message", CREATED_AT.isoformat()),
        )
        return
    connection.execute(
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
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?)
        """,
        (
            conversation_id,
            turn_id,
            role,
            route,
            answer_kind,
            "message",
            CREATED_AT.isoformat(),
        ),
    )
