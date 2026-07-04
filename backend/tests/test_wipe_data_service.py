from __future__ import annotations

from pathlib import Path

import pytest
from app.config import AppSettings
from app.services.wipe_data import (
    APP_OWNED_DATA_DIR_MARKER,
    UnsafeWipeTargetError,
    wipe_local_data,
)


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite+aiosqlite:///{data_dir / 'jobtracker.sqlite3'}",
        fernet_key_file=data_dir / "fernet.key",
    )


def test_wipe_local_data_removes_data_dir_and_reports_deleted_path(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir()
    (settings.data_dir / APP_OWNED_DATA_DIR_MARKER).touch()
    (settings.data_dir / "jobtracker.sqlite3").write_text("db")
    (settings.data_dir / "derived.txt").write_text("derived")

    result = wipe_local_data(settings)

    assert not settings.data_dir.exists()
    assert str(settings.data_dir.resolve()) in result.deleted_paths
    assert result.missing_paths == []
    assert result.status == "wiped"


def test_wipe_local_data_is_idempotent_when_targets_are_missing(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)

    result = wipe_local_data(settings)

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

    result = wipe_local_data(settings)

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

    result = wipe_local_data(settings)

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
        wipe_local_data(settings)

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
        wipe_local_data(settings)

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
        wipe_local_data(settings)

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
        wipe_local_data(settings)

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
        wipe_local_data(settings)

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
        wipe_local_data(settings)


def test_wipe_local_data_refuses_current_working_directory_parent() -> None:
    settings = AppSettings(
        _env_file=None,
        data_dir=Path.cwd().parent,
        database_url="sqlite+aiosqlite:///./.jobtracker/jobtracker.sqlite3",
    )

    with pytest.raises(UnsafeWipeTargetError):
        wipe_local_data(settings)
