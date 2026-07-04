from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import LOCAL_SQLITE_SCHEMES, AppSettings

SQLITE_BUSY_TIMEOUT_MS = 5000


def create_sqlite_engine(settings: AppSettings) -> AsyncEngine:
    """Create the app's async SQLite engine with Phase 0 connection conventions."""

    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(settings.database_url)
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


def sqlite_database_path(database_url: str) -> Path:
    """Return the file path represented by a local SQLite database URL."""

    parsed = urlsplit(database_url)
    if parsed.scheme not in LOCAL_SQLITE_SCHEMES or parsed.netloc:
        raise ValueError("database_url must use a file-backed local SQLite URL")

    raw_path = unquote(parsed.path)
    if raw_path in {"", "/", "/:memory:"}:
        raise ValueError("database_url must use a file-backed local SQLite URL")
    if raw_path.startswith("//"):
        return Path(raw_path[1:])
    if raw_path.startswith("/"):
        return Path(raw_path[1:])
    return Path(raw_path)


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
