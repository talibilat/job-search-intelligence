from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from .api import api_router
from .api.errors import register_exception_handlers
from .config import AppSettings, get_settings
from .services.sync_service import (
    ScheduledJobScheduler,
    SyncJob,
    SyncScheduler,
    noop_sync_job,
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
    resolved_sync_job = sync_job or noop_sync_job
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
