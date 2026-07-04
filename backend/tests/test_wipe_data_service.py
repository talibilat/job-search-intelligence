from __future__ import annotations

from pathlib import Path

import pytest
from app.config import AppSettings
from app.services.wipe_data import UnsafeWipeTargetError, wipe_local_data


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
    (settings.data_dir / "jobtracker.sqlite3").write_text("db")
    (settings.data_dir / "derived.txt").write_text("derived")

    result = wipe_local_data(settings)

    assert not settings.data_dir.exists()
    assert str(settings.data_dir.resolve()) in result.deleted_paths
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
