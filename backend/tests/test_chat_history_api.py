from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def test_get_chat_history_returns_persisted_messages(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_chat_message(connection, 1, "conversation-2", "user", "Other thread")
        insert_chat_message(
            connection,
            2,
            "conversation-1",
            "user",
            "Who am I waiting on?",
        )
        insert_chat_message(
            connection,
            3,
            "conversation-1",
            "assistant",
            "You are waiting on Example Co.",
            citations_json='[{"application_id":"app-1"}]',
            tool_outputs_json='[{"tool":"structured_query"}]',
        )
        connection.commit()
    client = create_test_client(database_path)

    response = client.get("/chat/history", params={"conversation_id": "conversation-1"})

    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "id": 2,
            "conversation_id": "conversation-1",
            "role": "user",
            "content": "Who am I waiting on?",
            "citations_json": [],
            "tool_outputs_json": [],
            "created_at": "2026-07-09T12:00:00Z",
        },
        {
            "id": 3,
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "You are waiting on Example Co.",
            "citations_json": [{"application_id": "app-1"}],
            "tool_outputs_json": [{"tool": "structured_query"}],
            "created_at": "2026-07-09T12:00:00Z",
        },
    ]


def test_get_chat_history_limits_results(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_chat_message(connection, 1, "conversation-1", "user", "First")
        insert_chat_message(connection, 2, "conversation-1", "assistant", "Second")
        connection.commit()
    client = create_test_client(database_path)

    response = client.get("/chat/history", params={"limit": 1})

    assert response.status_code == 200
    assert [message["id"] for message in response.json()["messages"]] == [1]


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def create_test_client(database_path: Path) -> TestClient:
    app = create_app(
        settings=AppSettings(_env_file=None, database_url=f"sqlite:///{database_path}")
    )
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite:///{database_path}",
    )
    return TestClient(app)


def insert_chat_message(
    connection: sqlite3.Connection,
    message_id: int,
    conversation_id: str,
    role: str,
    content: str,
    *,
    citations_json: str = "[]",
    tool_outputs_json: str = "[]",
) -> None:
    connection.execute(
        """
        INSERT INTO chat_messages (
            id,
            conversation_id,
            role,
            content,
            citations_json,
            tool_outputs_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            conversation_id,
            role,
            content,
            citations_json,
            tool_outputs_json,
            CREATED_AT.isoformat(),
        ),
    )
