from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime

from app.db.repositories.base import BaseRepository


class OAuthStateRepository(BaseRepository[object]):
    """Store single-use OAuth CSRF nonces locally across backend restarts."""

    def save_state(self, state: str, *, expires_at: datetime) -> None:
        self.execute(
            """
            INSERT INTO oauth_authorization_states (state_hash, expires_at, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_hash) DO UPDATE SET
                expires_at = excluded.expires_at,
                created_at = excluded.created_at
            """,
            (_state_hash(state), expires_at.isoformat(), datetime.now(UTC).isoformat()),
        )
        self.connection.commit()

    def consume_state(self, state: str, *, now: datetime) -> bool:
        cursor = self.execute(
            """
            DELETE FROM oauth_authorization_states
            WHERE state_hash = ? AND expires_at >= ?
            """,
            (_state_hash(state), now.isoformat()),
        )
        self.execute(
            "DELETE FROM oauth_authorization_states WHERE expires_at < ?",
            (now.isoformat(),),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def map_row(self, row: sqlite3.Row) -> object:
        del row
        raise AssertionError("OAuth states are only written or consumed.")


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()
