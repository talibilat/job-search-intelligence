from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import EmailProviderName
from app.db.repositories import SyncStateRepository
from app.providers.email import EmailAccountRef, EmailProviderCursor
from app.services.sync_service import SyncService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 9, 0, tzinfo=UTC)


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def test_sync_service_persists_latest_gmail_history_id(tmp_path: Path) -> None:
    repository = SyncStateRepository(migrated_connection(tmp_path))
    service = SyncService(sync_state_repository=repository)
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")

    service.store_sync_cursor(
        EmailProviderCursor(account=account, value="history-10", issued_at=NOW),
        updated_at=NOW + timedelta(seconds=1),
    )
    service.store_sync_cursor(
        EmailProviderCursor(
            account=account,
            value="history-11",
            issued_at=NOW + timedelta(minutes=1),
        ),
        updated_at=NOW + timedelta(minutes=1, seconds=1),
    )

    persisted_cursor = service.get_sync_cursor(account)

    assert persisted_cursor is not None
    assert persisted_cursor.account == account
    assert persisted_cursor.value == "history-11"
    assert persisted_cursor.issued_at == NOW + timedelta(minutes=1)

    row = repository.connection.execute("SELECT COUNT(*) FROM email_sync_state").fetchone()
    assert row is not None
    assert row[0] == 1


def test_sync_state_is_scoped_by_gmail_account(tmp_path: Path) -> None:
    repository = SyncStateRepository(migrated_connection(tmp_path))
    service = SyncService(sync_state_repository=repository)
    first_account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    second_account = EmailAccountRef(
        provider=EmailProviderName.GMAIL,
        account_id="other@example.com",
    )

    service.store_sync_cursor(
        EmailProviderCursor(account=first_account, value="history-10", issued_at=NOW),
        updated_at=NOW,
    )
    service.store_sync_cursor(
        EmailProviderCursor(account=second_account, value="history-20", issued_at=NOW),
        updated_at=NOW,
    )

    first_cursor = service.get_sync_cursor(first_account)
    second_cursor = service.get_sync_cursor(second_account)

    assert first_cursor is not None
    assert first_cursor.value == "history-10"
    assert second_cursor is not None
    assert second_cursor.value == "history-20"


def test_sync_state_repository_does_not_create_missing_schema() -> None:
    repository = SyncStateRepository(sqlite3.connect(":memory:"))
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")

    with pytest.raises(sqlite3.OperationalError, match="no such table: email_sync_state"):
        repository.fetch_state(account)


def test_alembic_upgrade_creates_email_sync_state_table(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }

    assert "email_sync_state" in table_names
