from __future__ import annotations

from inspect import iscoroutinefunction
from pathlib import Path

from app.api.wipe_data import wipe_data
from app.config import AppSettings, get_settings
from app.main import create_app
from app.services.wipe_data import APP_OWNED_DATA_DIR_MARKER
from fastapi.testclient import TestClient


def test_wipe_data_requires_exact_confirmation_phrase() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/local-data/wipe",
        json={"confirmation": "delete"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_wipe_data_endpoint_is_sync_to_avoid_blocking_event_loop() -> None:
    assert not iscoroutinefunction(wipe_data)


def test_wipe_data_endpoint_deletes_configured_local_data(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    (data_dir / "jobtracker.sqlite3").write_text("db")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{data_dir / 'jobtracker.sqlite3'}",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    response = client.post(
        "/local-data/wipe",
        json={"confirmation": "wipe-local-data"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "wiped"
    assert str(data_dir.resolve()) in response.json()["deleted_paths"]
    assert not data_dir.exists()


def test_wipe_data_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/local-data/wipe"]["post"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    bad_request_schema = operation["responses"]["400"]["content"]["application/json"]["schema"]
    validation_schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/WipeDataResponse"
    assert bad_request_schema["$ref"] == "#/components/schemas/ApiErrorResponse"
    assert validation_schema["$ref"] == "#/components/schemas/ApiErrorResponse"


def test_wipe_data_endpoint_returns_typed_error_for_unsafe_target() -> None:
    settings = AppSettings(
        _env_file=None,
        data_dir=Path.cwd(),
        database_url="sqlite+aiosqlite:///./.jobtracker/jobtracker.sqlite3",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    response = client.post(
        "/local-data/wipe",
        json={"confirmation": "wipe-local-data"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Configured local data path is not safe to wipe.",
            "details": [],
        },
    }
