from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.config import AppSettings
from app.security import (
    FernetSecretStore,
    KeyringSecretStore,
    SecretKind,
    SecretRef,
    SecretStoreUnavailableError,
)
from app.services.wipe_data import (
    APP_OWNED_DATA_DIR_MARKER,
    UnsafeWipeTargetError,
    WipeSecretDeletionError,
    wipe_local_data,
)
from pydantic import SecretStr


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{data_dir / 'jobtracker.sqlite3'}",
        fernet_key_file=data_dir / "fernet.key",
    )


class NoOpSecretStore:
    async def get_secret(self, ref: SecretRef):
        del ref
        return None

    async def set_secret(self, ref: SecretRef, value):
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        del ref


def run_wipe(settings: AppSettings):
    return asyncio.run(
        wipe_local_data(
            settings,
            secret_store=NoOpSecretStore(),
            connection_secret_refs=[],
        )
    )


def test_wipe_local_data_removes_data_dir_and_reports_deleted_path(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir()
    (settings.data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    (settings.data_dir / "jobtracker.sqlite3").write_text("db")
    (settings.data_dir / "derived.txt").write_text("derived")

    result = run_wipe(settings)

    assert not settings.data_dir.exists()
    assert str(settings.data_dir.resolve()) in result.deleted_paths
    assert result.missing_paths == []
    assert result.status == "wiped"


def test_wipe_local_data_is_idempotent_when_targets_are_missing(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)

    result = run_wipe(settings)

    assert result.status == "wiped"
    assert str(settings.data_dir.resolve()) in result.missing_paths


def test_wipe_local_data_removes_external_sqlite_sidecars(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    database = tmp_path / "external" / "jobtracker.sqlite3"
    database.parent.mkdir()
    database.write_text("db")
    database.with_name(f"{database.name}-wal").write_text("wal")
    database.with_name(f"{database.name}-shm").write_text("shm")
    database.with_name(f"{database.name}-journal").write_text("journal")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{database}",
        fernet_key_file=data_dir / "fernet.key",
    )

    result = run_wipe(settings)

    assert not database.exists()
    assert not database.with_name(f"{database.name}-wal").exists()
    assert not database.with_name(f"{database.name}-shm").exists()
    assert not database.with_name(f"{database.name}-journal").exists()
    assert str(database.resolve()) in result.deleted_paths


def test_wipe_local_data_removes_external_sqlite_path_with_parent_segment(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    database = tmp_path / "jobtracker.sqlite3"
    database.write_text("db")
    database.with_name(f"{database.name}-wal").write_text("wal")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{data_dir / '..' / database.name}",
        fernet_key_file=data_dir / "fernet.key",
    )

    result = run_wipe(settings)

    assert not data_dir.exists()
    assert not database.exists()
    assert not database.with_name(f"{database.name}-wal").exists()
    assert str(database.resolve()) in result.deleted_paths


def test_wipe_local_data_refuses_directory_at_external_sqlite_path(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    database = tmp_path / "external" / "jobtracker.sqlite3"
    database.mkdir(parents=True)
    (database / "unrelated.txt").write_text("unrelated")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{database}",
        fernet_key_file=data_dir / "fernet.key",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)

    assert database.exists()
    assert (database / "unrelated.txt").exists()


def test_wipe_local_data_refuses_data_dir_that_is_regular_file(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.write_text("unrelated")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{data_dir / 'jobtracker.sqlite3'}",
        fernet_key_file=data_dir / "fernet.key",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)

    assert data_dir.exists()
    assert data_dir.read_text() == "unrelated"


def test_wipe_local_data_refuses_sqlite_symlink_outside_data_dir(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / ".jobtracker"
    data_dir.mkdir()
    external_database = tmp_path / "external.sqlite3"
    external_database.write_text("external db")
    database = data_dir / "jobtracker.sqlite3"
    database.symlink_to(external_database)
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{database}",
        fernet_key_file=data_dir / "fernet.key",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)

    assert data_dir.exists()
    assert database.is_symlink()
    assert external_database.exists()
    assert external_database.read_text() == "external db"


def test_wipe_local_data_preflights_all_targets_before_deleting(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "derived.txt").write_text("derived")
    database = tmp_path / "external" / "jobtracker.sqlite3"
    database.mkdir(parents=True)
    (database / "unrelated.txt").write_text("unrelated")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{database}",
        fernet_key_file=data_dir / "fernet.key",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)

    assert data_dir.exists()
    assert (data_dir / "derived.txt").exists()
    assert database.exists()
    assert (database / "unrelated.txt").exists()


def test_wipe_local_data_refuses_unmarked_custom_data_dir_before_deleting(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "Documents"
    data_dir.mkdir()
    (data_dir / "unrelated.txt").write_text("unrelated")
    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{data_dir / 'jobtracker.sqlite3'}",
        fernet_key_file=data_dir / "fernet.key",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)

    assert data_dir.exists()
    assert (data_dir / "unrelated.txt").exists()


@pytest.mark.parametrize("target", [Path("/"), Path.home(), Path.cwd()])
def test_wipe_local_data_refuses_unsafe_data_dir(target: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        data_dir=target,
        database_url="sqlite+aiosqlite:///./.jobtracker/jobtracker.sqlite3",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)


def test_wipe_local_data_refuses_current_working_directory_parent() -> None:
    settings = AppSettings(
        _env_file=None,
        data_dir=Path.cwd().parent,
        database_url="sqlite+aiosqlite:///./.jobtracker/jobtracker.sqlite3",
    )

    with pytest.raises(UnsafeWipeTargetError):
        run_wipe(settings)


class RecordingKeyringBackend:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.passwords.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.passwords[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self.events.append(username)
        self.passwords.pop((service_name, username), None)


class FailingSecretStore:
    def __init__(self, raw_secret: str) -> None:
        self.raw_secret = raw_secret

    async def get_secret(self, ref: SecretRef):
        del ref
        return None

    async def set_secret(self, ref: SecretRef, value):
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        del ref
        raise SecretStoreUnavailableError(f"could not delete {self.raw_secret}")


def test_wipe_local_data_deletes_connection_and_configured_secrets_before_files(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir()
    (settings.data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    database = settings.data_dir / "jobtracker.sqlite3"
    database.write_text("db")
    events: list[str] = []
    keyring = RecordingKeyringBackend(events)
    store = KeyringSecretStore(keyring_backend=keyring)
    connection_ref = SecretRef(
        kind=SecretKind.OAUTH_TOKEN,
        provider="gmail",
        name="person-example.com",
    )

    result = asyncio.run(
        wipe_local_data(settings, secret_store=store, connection_secret_refs=[connection_ref])
    )

    assert result.status == "wiped"
    assert not settings.data_dir.exists()
    assert any("person-example.com" in event for event in events)
    assert any("azure_openai" in event and "api_key" in event for event in events)
    assert any("gmail" in event and "refresh_token" in event for event in events)


def test_wipe_local_data_keeps_files_when_secret_deletion_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir()
    (settings.data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    database = settings.data_dir / "jobtracker.sqlite3"
    database.write_text("db")
    raw_secret = "do-not-expose-this-secret"

    with pytest.raises(WipeSecretDeletionError) as error_info:
        asyncio.run(
            wipe_local_data(
                settings,
                secret_store=FailingSecretStore(raw_secret),
                connection_secret_refs=[],
            )
        )

    assert settings.data_dir.exists()
    assert database.exists()
    assert raw_secret not in str(error_info.value)
    assert error_info.value.__cause__ is None


def test_wipe_local_data_deletes_fernet_secrets_before_local_files(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.fernet_key_file = tmp_path / "outside-data" / "fernet.key"
    settings.data_dir.mkdir()
    (settings.data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    (settings.data_dir / "jobtracker.sqlite3").write_text("db")
    store = FernetSecretStore.from_settings(settings)
    connection_ref = SecretRef(
        kind=SecretKind.OAUTH_TOKEN,
        provider="gmail",
        name="person-example.com",
    )
    asyncio.run(store.set_secret(connection_ref, SecretStr("gmail-token")))

    result = asyncio.run(
        wipe_local_data(
            settings,
            secret_store=store,
            connection_secret_refs=[connection_ref],
        )
    )

    assert result.status == "wiped"
    assert not settings.data_dir.exists()
    assert asyncio.run(store.get_secret(connection_ref)) is None
