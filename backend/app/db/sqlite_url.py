from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.config import LOCAL_SQLITE_SCHEMES

ASYNC_SQLITE_SCHEME = "sqlite+aiosqlite"


def sqlite_database_path(database_url: str) -> Path:
    """Return the filesystem path for a file-backed local SQLite URL."""

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


def sqlite_async_database_url(database_url: str) -> str:
    """Normalize a local SQLite URL to SQLAlchemy's aiosqlite async scheme."""

    sqlite_database_path(database_url)
    parsed = urlsplit(database_url)
    if parsed.scheme == ASYNC_SQLITE_SCHEME:
        return database_url

    async_url = f"{ASYNC_SQLITE_SCHEME}://{parsed.path}"
    if parsed.query:
        async_url = f"{async_url}?{parsed.query}"
    if parsed.fragment:
        async_url = f"{async_url}#{parsed.fragment}"
    return async_url


def sqlite_sync_database_url(database_url: str) -> str:
    """Normalize a local SQLite URL to SQLAlchemy's synchronous SQLite scheme."""

    sqlite_database_path(database_url)
    parsed = urlsplit(database_url)
    if parsed.scheme == "sqlite":
        return database_url

    sync_url = f"sqlite://{parsed.path}"
    if parsed.query:
        sync_url = f"{sync_url}?{parsed.query}"
    if parsed.fragment:
        sync_url = f"{sync_url}#{parsed.fragment}"
    return sync_url
