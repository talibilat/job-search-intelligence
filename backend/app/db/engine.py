from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import AppSettings
from app.db.sqlite_url import sqlite_async_database_url, sqlite_database_path

SQLITE_BUSY_TIMEOUT_MS = 5000


def create_sqlite_engine(settings: AppSettings) -> AsyncEngine:
    """Create the app's async SQLite engine with Phase 0 connection conventions."""

    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(sqlite_async_database_url(settings.database_url))
    _register_sqlite_connection_pragmas(engine)
    return engine


async def dispose_sqlite_engine(engine: AsyncEngine) -> None:
    """Close pooled database connections owned by an async SQLite engine."""

    await engine.dispose()


@asynccontextmanager
async def sqlite_transaction(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Open an async transaction for repository or service database work."""

    async with engine.begin() as connection:
        yield connection


def _register_sqlite_connection_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()
