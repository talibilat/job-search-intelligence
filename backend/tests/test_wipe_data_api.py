from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from app.api.dependencies import get_email_connection_secret_refs
from app.api.sync import EmailSyncStatusStore, get_sync_status_store
from app.api.wipe_data import get_wipe_secret_store
from app.config import AppSettings, get_settings
from app.main import create_app
from app.security import SecretRef, SecretStore, SecretStoreUnavailableError
from app.services.wipe_data import APP_OWNED_DATA_DIR_MARKER
from fastapi.testclient import TestClient
from pydantic import SecretStr


class NoOpSecretStore:
    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        del ref
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        del ref


def test_wipe_data_requires_exact_confirmation_phrase() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/local-data/wipe",
        json={"confirmation": "delete"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_wipe_data_rejects_unexpected_payload_fields(tmp_path: Path) -> None:
    data_dir, marker_file, client = create_wipe_data_test_client(tmp_path)

    response = client.post(
        "/local-data/wipe",
        json={
            "confirmation": "wipe-local-data",
            "delete_external_backups": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert marker_file.exists()


def test_wipe_data_endpoint_deletes_configured_local_data(
    tmp_path: Path,
) -> None:
    status_store = EmailSyncStatusStore()
    data_dir, _marker_file, client = create_wipe_data_test_client(
        tmp_path,
        status_store=status_store,
    )

    response = client.post(
        "/local-data/wipe",
        json={"confirmation": "wipe-local-data"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "wiped"
    assert str(data_dir.resolve()) in response.json()["deleted_paths"]
    assert not data_dir.exists()
    assert status_store.try_acquire_run()
    status_store.release_run()


def test_wipe_data_secret_failure_is_typed_sanitized_and_keeps_local_data(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_secret = "do-not-expose-this-secret"

    class FailingStore:
        async def get_secret(self, ref: SecretRef) -> SecretStr | None:
            del ref
            return None

        async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
            del ref, value

        async def delete_secret(self, ref: SecretRef) -> None:
            del ref
            raise SecretStoreUnavailableError(raw_secret)

    status_store = EmailSyncStatusStore()
    data_dir, marker_file, client = create_wipe_data_test_client(
        tmp_path,
        secret_store=FailingStore(),
        status_store=status_store,
    )

    response = client.post("/local-data/wipe", json={"confirmation": "wipe-local-data"})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Stored credentials could not be deleted. Local data was not changed.",
            "details": [],
        }
    }
    assert data_dir.exists()
    assert marker_file.exists()
    assert raw_secret not in response.text
    assert raw_secret not in caplog.text
    assert status_store.try_acquire_run()
    status_store.release_run()


def create_wipe_data_test_client(
    tmp_path: Path,
    *,
    secret_store: SecretStore | None = None,
    status_store: EmailSyncStatusStore | None = None,
    connection_secret_refs_resolver: Callable[[], list[SecretRef]] | None = None,
) -> tuple[Path, Path, TestClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    marker_file = data_dir / "jobtracker.sqlite3"
    marker_file.write_text("db")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{marker_file}",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_wipe_secret_store] = lambda: secret_store or NoOpSecretStore()
    app.dependency_overrides[get_email_connection_secret_refs] = (
        connection_secret_refs_resolver or (lambda: [])
    )
    if status_store is not None:
        app.dependency_overrides[get_sync_status_store] = lambda: status_store
    return data_dir, marker_file, TestClient(app)


def test_wipe_data_conflicts_with_active_sync(tmp_path: Path) -> None:
    status_store = EmailSyncStatusStore()
    assert status_store.try_acquire_run()
    data_dir, marker_file, client = create_wipe_data_test_client(
        tmp_path,
        status_store=status_store,
    )

    response = client.post("/local-data/wipe", json={"confirmation": "wipe-local-data"})

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "Email sync or local data deletion is already running. Try again later.",
            "details": [],
        },
    }
    assert data_dir.exists()
    assert marker_file.exists()
    status_store.release_run()


def test_wipe_data_acquires_lock_before_resolving_connection_secrets(
    tmp_path: Path,
) -> None:
    status_store = EmailSyncStatusStore()
    lock_observations: list[bool] = []

    def resolve_connection_secret_refs() -> list[SecretRef]:
        acquired = status_store.try_acquire_run()
        lock_observations.append(not acquired)
        if acquired:
            status_store.release_run()
        return []

    _data_dir, _marker_file, client = create_wipe_data_test_client(
        tmp_path,
        status_store=status_store,
        connection_secret_refs_resolver=resolve_connection_secret_refs,
    )

    response = client.post("/local-data/wipe", json={"confirmation": "wipe-local-data"})

    assert response.status_code == 200
    assert lock_observations == [True]


def test_wipe_data_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/local-data/wipe"]["post"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    bad_request_schema = operation["responses"]["400"]["content"]["application/json"]["schema"]
    validation_schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    unavailable_schema = operation["responses"]["503"]["content"]["application/json"]["schema"]
    conflict_schema = operation["responses"]["409"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/WipeDataResponse"
    assert bad_request_schema["$ref"] == "#/components/schemas/ApiErrorResponse"
    assert validation_schema["$ref"] == "#/components/schemas/ApiErrorResponse"
    assert unavailable_schema["$ref"] == "#/components/schemas/ApiErrorResponse"
    assert conflict_schema["$ref"] == "#/components/schemas/ApiErrorResponse"


def test_wipe_data_endpoint_returns_typed_error_for_unsafe_target() -> None:
    settings = AppSettings(
        _env_file=None,
        data_dir=Path.cwd(),
        database_url="sqlite+aiosqlite:///./.jobtracker/jobtracker.sqlite3",
    )
    status_store = EmailSyncStatusStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_wipe_secret_store] = lambda: NoOpSecretStore()
    app.dependency_overrides[get_email_connection_secret_refs] = lambda: []
    app.dependency_overrides[get_sync_status_store] = lambda: status_store
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
    assert status_store.try_acquire_run()
    status_store.release_run()
