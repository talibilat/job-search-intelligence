from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import Engine, engine_from_config, event, pool

from app.config import AppSettings
from app.db.engine import load_sqlite_vec_sync, verify_sqlite_vec
from app.db.migrations.config import migration_context_options
from app.db.sqlite_url import sqlite_database_path, sqlite_sync_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None
DEFAULT_DATABASE_URL = str(AppSettings.model_fields["database_url"].default)
ALEMBIC_FALLBACK_DATABASE_URL = "sqlite+aiosqlite:///./.jobtracker/jobtracker.sqlite3"


def database_url() -> str:
    """Return a synchronous SQLite URL for Alembic's migration engine."""

    settings_url = AppSettings().database_url
    configured_url = context.config.get_main_option("sqlalchemy.url")
    if configured_url and configured_url not in {
        DEFAULT_DATABASE_URL,
        ALEMBIC_FALLBACK_DATABASE_URL,
    }:
        return sqlite_sync_database_url(configured_url)

    return sqlite_sync_database_url(settings_url)


def run_migrations_offline() -> None:
    """Run migrations without creating an engine."""

    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **migration_context_options(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a synchronous SQLAlchemy engine."""

    sqlite_path = sqlite_database_path(database_url())
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    current_config = context.config
    configuration = current_config.get_section(current_config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    settings = AppSettings()
    _register_sqlite_vec_loader(connectable, settings.sqlite_vec_extension_path)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **migration_context_options(),
        )

        with context.begin_transaction():
            context.run_migrations()


def _register_sqlite_vec_loader(
    connectable: Engine,
    sqlite_vec_extension_path: Path | None,
) -> None:
    @event.listens_for(connectable, "connect")
    def load_sqlite_vec(dbapi_connection: Any, _connection_record: Any) -> None:
        load_sqlite_vec_sync(dbapi_connection, sqlite_vec_extension_path)
        verify_sqlite_vec(dbapi_connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
