import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import app.main as main


def test_create_app_returns_fastapi_application() -> None:
    created_app = main.create_app()

    assert isinstance(created_app, FastAPI)
    assert isinstance(main.app, FastAPI)


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
