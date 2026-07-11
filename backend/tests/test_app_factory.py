import asyncio
from unittest.mock import AsyncMock

import app.main as main
import pytest
from app.config import AppSettings
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


class RecordingScheduler:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_wait: bool | None = None

    def add_job(
        self,
        func: object,
        trigger: str,
        *,
        seconds: int,
        id: str,
        replace_existing: bool,
        next_run_time: object = None,
    ) -> None:
        return None

    def remove_job(self, job_id: str) -> None:
        return None

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, wait: bool) -> None:
        self.shutdown_wait = wait


def test_create_app_returns_fastapi_application() -> None:
    created_app = main.create_app()

    assert isinstance(created_app, FastAPI)
    assert isinstance(main.app, FastAPI)


def test_create_app_uses_configured_sync_job_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_job = AsyncMock()
    monkeypatch.setattr(main, "create_configured_sync_job", lambda settings: configured_job)

    app = main.create_app(settings=AppSettings(_env_file=None))

    with TestClient(app):
        scheduler = app.state.sync_scheduler
        assert scheduler.sync_job is configured_job


def test_create_app_registers_api_router(monkeypatch: pytest.MonkeyPatch) -> None:
    probe_router = APIRouter()

    @probe_router.get("/__router_probe")
    def router_probe() -> dict[str, str]:
        return {"status": "registered"}

    monkeypatch.setattr(main, "api_router", probe_router)

    client = TestClient(main.create_app())

    response = client.get("/__router_probe")
    assert response.status_code == 200
    assert response.json() == {"status": "registered"}


def test_create_app_starts_and_stops_sync_scheduler_during_lifespan() -> None:
    scheduler = RecordingScheduler()
    settings = AppSettings(_env_file=None, sync_on_open=True, sync_interval_seconds=120)

    async def sync_job() -> None:
        return None

    app = main.create_app(settings=settings, sync_job=sync_job, scheduler=scheduler)

    assert scheduler.started is False

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            assert scheduler.started is True
            assert scheduler.shutdown_wait is None

    asyncio.run(run_lifespan())

    assert scheduler.shutdown_wait is False


def test_create_app_keeps_sync_scheduler_running_when_job_disabled() -> None:
    scheduler = RecordingScheduler()
    settings = AppSettings(_env_file=None, sync_on_open=False, sync_interval_seconds=120)

    async def sync_job() -> None:
        raise AssertionError("disabled scheduler must not run sync")

    app = main.create_app(settings=settings, sync_job=sync_job, scheduler=scheduler)

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            assert scheduler.started is True

    asyncio.run(run_lifespan())

    assert scheduler.shutdown_wait is False
