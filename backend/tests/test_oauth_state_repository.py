from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.repositories.oauth_state import OAuthStateRepository
from app.services.gmail_auth import SQLiteOAuthStateStore


def test_oauth_state_survives_new_store_and_is_single_use(tmp_path: Path) -> None:
    database_path = tmp_path / "oauth.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE oauth_authorization_states (
                state_hash TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        now = datetime(2026, 7, 15, 12, tzinfo=UTC)
        SQLiteOAuthStateStore(
            OAuthStateRepository(connection),
            clock=lambda: now,
        ).save_state("state-a")
        restarted_store = SQLiteOAuthStateStore(
            OAuthStateRepository(connection),
            clock=lambda: now,
        )
        assert restarted_store.consume_state("state-a") is True
        assert restarted_store.consume_state("state-a") is False


def test_oauth_state_expires(tmp_path: Path) -> None:
    database_path = tmp_path / "oauth.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE oauth_authorization_states (
                state_hash TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        now = datetime(2026, 7, 15, 12, tzinfo=UTC)
        SQLiteOAuthStateStore(
            OAuthStateRepository(connection),
            ttl=timedelta(seconds=1),
            clock=lambda: now,
        ).save_state("state-a")
        expired_store = SQLiteOAuthStateStore(
            OAuthStateRepository(connection),
            clock=lambda: now + timedelta(seconds=2),
        )
        assert expired_store.consume_state("state-a") is False
