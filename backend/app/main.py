from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from .api import api_router
from .api.errors import register_exception_handlers
from .api.sync import create_configured_sync_job
from .config import AppSettings, get_settings
from .db.repositories import ProviderConfigurationRepository
from .db.sqlite_url import sqlite_database_path
from .security import create_secret_store
from .services.provider_config import (
    apply_persisted_provider_config,
    import_azure_openai_api_key_from_environment,
)
from .services.sync_service import (
    ScheduledJobScheduler,
    SyncJob,
    SyncScheduler,
)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None, bool | None]]


def create_lifespan(
    *,
    settings: AppSettings,
    sync_job: SyncJob,
    scheduler: ScheduledJobScheduler | None,
) -> Lifespan:
    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        await import_azure_openai_api_key_from_environment(create_secret_store(settings))
        sync_scheduler = SyncScheduler(
            sync_on_open=settings.sync_on_open,
            interval_seconds=settings.sync_interval_seconds,
            sync_job=sync_job,
            scheduler=scheduler,
        )
        fastapi_app.state.sync_scheduler = sync_scheduler
        sync_scheduler.start()
        try:
            yield
        finally:
            sync_scheduler.shutdown()

    return lifespan


def create_app(
    *,
    settings: AppSettings | None = None,
    sync_job: SyncJob | None = None,
    scheduler: ScheduledJobScheduler | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    database_path = sqlite_database_path(resolved_settings.database_url)
    if database_path.is_file():
        connection = sqlite3.connect(database_path)
        try:
            apply_persisted_provider_config(
                resolved_settings,
                ProviderConfigurationRepository(connection).fetch(),
            )
        finally:
            connection.close()
    resolved_sync_job = sync_job or create_configured_sync_job(resolved_settings)
    fastapi_app = FastAPI(
        title="Job Search Intelligence API",
        lifespan=create_lifespan(
            settings=resolved_settings,
            sync_job=resolved_sync_job,
            scheduler=scheduler,
        ),
    )
    fastapi_app.include_router(api_router)
    register_exception_handlers(fastapi_app)
    return fastapi_app


app = create_app()
