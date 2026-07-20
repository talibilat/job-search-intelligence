from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config import AppSettings
from app.db.sqlite_url import sqlite_database_path
from app.providers.registry import provider_registry
from app.security import TAVILY_API_KEY_REF, SecretRef, SecretStore, SecretStoreError

APP_OWNED_DATA_DIR_MARKER = ".jobtracker-data"


@dataclass(frozen=True)
class WipeDataResult:
    status: Literal["wiped"] = "wiped"
    deleted_paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)


class UnsafeWipeTargetError(ValueError):
    """Raised when configured storage points at a dangerous filesystem path."""


class WipeSecretDeletionError(RuntimeError):
    """Raised without secret-store details when credentials cannot be deleted."""


async def wipe_local_data(
    settings: AppSettings,
    *,
    secret_store: SecretStore,
    connection_secret_refs: list[SecretRef],
) -> WipeDataResult:
    """Delete app secrets before deleting preflighted local storage targets."""

    targets = _wipe_targets(settings)
    data_dir = _target_path(settings.data_dir)
    deleted_paths: list[str] = []
    missing_paths: list[str] = []

    _preflight_wipe_targets(targets, data_dir)

    try:
        for ref in _wipe_secret_refs(connection_secret_refs):
            await secret_store.delete_secret(ref)
    except SecretStoreError:
        raise WipeSecretDeletionError("Configured secrets could not be deleted.") from None

    await asyncio.to_thread(_delete_targets, targets, data_dir, deleted_paths, missing_paths)

    return WipeDataResult(deleted_paths=deleted_paths, missing_paths=missing_paths)


def _delete_targets(
    targets: list[Path],
    data_dir: Path,
    deleted_paths: list[str],
    missing_paths: list[str],
) -> None:
    for target in targets:
        if not target.exists():
            missing_paths.append(str(target))
            continue

        if target == data_dir and target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        deleted_paths.append(str(target))


def _wipe_secret_refs(connection_secret_refs: list[SecretRef]) -> list[SecretRef]:
    refs = [
        *connection_secret_refs,
        TAVILY_API_KEY_REF,
        *(
            requirement.ref
            for provider in provider_registry.email_providers()
            for requirement in provider.secret_requirements
        ),
        *(
            requirement.ref
            for provider in provider_registry.llm_providers()
            for requirement in provider.secret_requirements
        ),
    ]
    unique: list[SecretRef] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        key = (ref.kind.value, ref.provider, ref.name)
        if key not in seen:
            unique.append(ref)
            seen.add(key)
    return unique


def _preflight_wipe_targets(targets: list[Path], data_dir: Path) -> None:
    canonical_data_dir = _canonical_path(data_dir)
    for target in targets:
        _validate_safe_target(target)
        if (
            target.exists()
            and target.is_symlink()
            and (target == data_dir or not _is_relative_to(target.resolve(), canonical_data_dir))
        ):
            raise UnsafeWipeTargetError(f"Unsafe wipe target: {target}")
        if target.exists() and target == data_dir and not target.is_dir():
            raise UnsafeWipeTargetError(f"Unsafe wipe target: {target}")
        if target.exists() and target.is_dir() and target == data_dir:
            _validate_app_owned_data_dir(target)
        if target.exists() and target.is_dir() and target != data_dir:
            raise UnsafeWipeTargetError(f"Unsafe wipe target: {target}")


def _validate_app_owned_data_dir(data_dir: Path) -> None:
    if data_dir.name == ".jobtracker":
        return
    if (data_dir / APP_OWNED_DATA_DIR_MARKER).is_file():
        return
    raise UnsafeWipeTargetError(f"Unsafe wipe target: {data_dir}")


def _wipe_targets(settings: AppSettings) -> list[Path]:
    data_dir = _target_path(settings.data_dir)
    canonical_data_dir = _canonical_path(settings.data_dir)
    targets = [data_dir]
    database_path = sqlite_database_path(settings.database_url)

    database_target = _target_path(database_path)
    canonical_database_path = _canonical_path(database_path)
    if _is_relative_to(canonical_database_path, canonical_data_dir):
        if (
            database_target.exists()
            and database_target.is_symlink()
            and not _is_relative_to(database_target.resolve(), canonical_data_dir)
        ):
            raise UnsafeWipeTargetError(f"Unsafe wipe target: {database_target}")
        return _deduplicate_paths(targets)

    targets.extend(_sqlite_file_targets(database_target))

    return _deduplicate_paths(targets)


def _sqlite_file_targets(database_path: Path) -> list[Path]:
    return [
        database_path,
        database_path.with_name(f"{database_path.name}-wal"),
        database_path.with_name(f"{database_path.name}-shm"),
        database_path.with_name(f"{database_path.name}-journal"),
    ]


def _deduplicate_paths(paths: list[Path]) -> list[Path]:
    deduplicated: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        target = _target_path(path)
        canonical = _canonical_path(path)
        if canonical not in seen:
            deduplicated.append(target)
            seen.add(canonical)
    return deduplicated


def _validate_safe_target(target: Path) -> None:
    resolved = target.resolve()
    if resolved in _unsafe_targets():
        raise UnsafeWipeTargetError(f"Unsafe wipe target: {resolved}")


def _canonical_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _target_path(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    if absolute.exists() and absolute.is_symlink():
        return absolute
    return _canonical_path(path)


def _unsafe_targets() -> set[Path]:
    current_working_directory = Path.cwd().resolve()
    return {
        Path("/").resolve(),
        Path.home().resolve(),
        current_working_directory,
        *current_working_directory.parents,
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
