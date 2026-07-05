from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
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
    _register_sqlite_connection_setup(engine, settings.sqlite_vec_extension_path)
    return engine


async def dispose_sqlite_engine(engine: AsyncEngine) -> None:
    """Close pooled database connections owned by an async SQLite engine."""

    await engine.dispose()


@asynccontextmanager
async def sqlite_transaction(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Open an async transaction for repository or service database work."""

    async with engine.begin() as connection:
        yield connection


def _register_sqlite_connection_setup(
    engine: AsyncEngine,
    sqlite_vec_extension_path: Path | None,
) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
        _load_sqlite_vec(dbapi_connection, sqlite_vec_extension_path)
        verify_sqlite_vec(dbapi_connection)
        _set_sqlite_pragmas(dbapi_connection)


def _set_sqlite_pragmas(dbapi_connection: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def _load_sqlite_vec(dbapi_connection: Any, sqlite_vec_extension_path: Path | None) -> None:
    extension_path = _sqlite_vec_extension_path(sqlite_vec_extension_path)
    dbapi_connection.run_async(
        lambda driver_connection: _load_sqlite_extension_async(
            driver_connection,
            extension_path,
        ),
    )


def load_sqlite_vec_sync(dbapi_connection: Any, sqlite_vec_extension_path: Path | None) -> None:
    extension_path = _sqlite_vec_extension_path(sqlite_vec_extension_path)
    _load_sqlite_extension_sync(dbapi_connection, extension_path)


def _sqlite_vec_extension_path(sqlite_vec_extension_path: Path | None) -> str:
    return str(sqlite_vec_extension_path or _bundled_sqlite_vec_extension_path())


async def _load_sqlite_extension_async(
    driver_connection: Any,
    extension_path: str,
) -> None:
    await driver_connection.enable_load_extension(True)
    try:
        await driver_connection.load_extension(extension_path)
    finally:
        await driver_connection.enable_load_extension(False)


def _load_sqlite_extension_sync(dbapi_connection: Any, extension_path: str) -> None:
    dbapi_connection.enable_load_extension(True)
    try:
        dbapi_connection.load_extension(extension_path)
    finally:
        dbapi_connection.enable_load_extension(False)


def verify_sqlite_vec(dbapi_connection: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT vec_version()")
    finally:
        cursor.close()


def _bundled_sqlite_vec_extension_path() -> str:
    sqlite_vec = import_module("sqlite_vec")
    loadable_path = getattr(sqlite_vec, "loadable_path", None)
    if not callable(loadable_path):
        raise RuntimeError("sqlite_vec.loadable_path is unavailable")

    extension_path = loadable_path()
    if not isinstance(extension_path, str):
        raise RuntimeError("sqlite_vec.loadable_path did not return a string path")

    return extension_path
