from __future__ import annotations

from pathlib import Path

import pytest
from app.config import AppSettings
from app.db.engine import create_sqlite_engine, dispose_sqlite_engine, sqlite_transaction
from app.db.sqlite_url import sqlite_database_path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def settings_for_database(database_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        data_dir=database_path.parent,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )


def settings_for_sync_database_url(database_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        data_dir=database_path.parent,
        database_url=f"sqlite:///{database_path}",
    )


@pytest.mark.anyio
async def test_create_sqlite_engine_returns_async_engine(tmp_path: Path) -> None:
    engine = create_sqlite_engine(settings_for_database(tmp_path / "jobtracker.sqlite3"))

    try:
        assert isinstance(engine, AsyncEngine)
    finally:
        await dispose_sqlite_engine(engine)


@pytest.mark.anyio
async def test_create_sqlite_engine_accepts_sync_sqlite_url(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    engine = create_sqlite_engine(settings_for_sync_database_url(database_path))

    try:
        async with sqlite_transaction(engine) as connection:
            await connection.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))

        assert database_path.exists()
    finally:
        await dispose_sqlite_engine(engine)


def test_sqlite_database_path_parses_file_backed_local_urls(tmp_path: Path) -> None:
    database_path = tmp_path / "nested path" / "jobtracker.sqlite3"

    assert sqlite_database_path(f"sqlite:///{database_path}") == database_path
    assert sqlite_database_path(f"sqlite+aiosqlite:///{database_path}") == database_path


@pytest.mark.anyio
async def test_sqlite_transaction_creates_parent_directory_and_persists_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "jobtracker.sqlite3"
    engine = create_sqlite_engine(settings_for_database(database_path))

    try:
        async with sqlite_transaction(engine) as connection:
            await connection.execute(
                text("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"),
            )
            await connection.execute(text("INSERT INTO widgets (name) VALUES ('alpha')"))

        async with sqlite_transaction(engine) as connection:
            result = await connection.execute(text("SELECT id, name FROM widgets"))
            rows = [dict(row) for row in result.mappings().all()]

        assert database_path.exists()
        assert rows == [{"id": 1, "name": "alpha"}]
    finally:
        await dispose_sqlite_engine(engine)


@pytest.mark.anyio
async def test_sqlite_engine_applies_phase_zero_pragmas(tmp_path: Path) -> None:
    engine = create_sqlite_engine(settings_for_database(tmp_path / "jobtracker.sqlite3"))

    try:
        async with sqlite_transaction(engine) as connection:
            foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
            journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
            synchronous = await connection.scalar(text("PRAGMA synchronous"))
            busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))

        assert foreign_keys == 1
        assert journal_mode == "wal"
        assert synchronous == 1
        assert busy_timeout == 5000
    finally:
        await dispose_sqlite_engine(engine)


@pytest.mark.anyio
async def test_sqlite_transaction_rolls_back_failed_work(tmp_path: Path) -> None:
    engine = create_sqlite_engine(settings_for_database(tmp_path / "jobtracker.sqlite3"))

    try:
        async with sqlite_transaction(engine) as connection:
            await connection.execute(
                text("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"),
            )

        with pytest.raises(RuntimeError, match="force rollback"):
            async with sqlite_transaction(engine) as connection:
                await connection.execute(text("INSERT INTO widgets (name) VALUES ('rolled-back')"))
                raise RuntimeError("force rollback")

        async with sqlite_transaction(engine) as connection:
            count = await connection.scalar(text("SELECT COUNT(*) FROM widgets"))

        assert count == 0
    finally:
        await dispose_sqlite_engine(engine)
