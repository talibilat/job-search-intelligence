from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.config import AppSettings
from app.security import (
    FernetSecretStore,
    SecretKind,
    SecretRef,
    SecretStore,
    SecretStoreUnavailableError,
)
from pydantic import SecretStr


def secret_ref() -> SecretRef:
    return SecretRef(
        kind=SecretKind.LLM_API_KEY,
        provider="azure_openai",
        name="api_key",
    )


def encrypted_secret_files(store_dir: Path) -> list[Path]:
    return sorted(path for path in store_dir.rglob("*") if path.is_file())


def test_fernet_store_satisfies_secret_store_protocol(tmp_path: Path) -> None:
    store = FernetSecretStore(
        key_file=tmp_path / "fernet.key",
        store_dir=tmp_path / "secrets",
    )

    assert isinstance(store, SecretStore)


def test_fernet_store_round_trips_without_plaintext_at_rest(tmp_path: Path) -> None:
    key_file = tmp_path / "fernet.key"
    store_dir = tmp_path / "secrets"
    store = FernetSecretStore(key_file=key_file, store_dir=store_dir)
    ref = secret_ref()
    raw_secret = "super-secret-api-key"

    asyncio.run(store.set_secret(ref, SecretStr(raw_secret)))

    stored = asyncio.run(store.get_secret(ref))
    assert stored is not None
    assert stored.get_secret_value() == raw_secret
    assert key_file.exists()
    assert raw_secret.encode() not in key_file.read_bytes()

    encrypted_files = encrypted_secret_files(store_dir)
    assert len(encrypted_files) == 1
    encrypted_bytes = encrypted_files[0].read_bytes()
    assert raw_secret.encode() not in encrypted_bytes
    assert encrypted_bytes.startswith(b"gAAAA")


def test_fernet_store_reopens_existing_key_and_encrypted_payload(tmp_path: Path) -> None:
    key_file = tmp_path / "fernet.key"
    store_dir = tmp_path / "secrets"
    first_store = FernetSecretStore(key_file=key_file, store_dir=store_dir)
    ref = secret_ref()

    asyncio.run(first_store.set_secret(ref, SecretStr("oauth-refresh-token")))

    second_store = FernetSecretStore(key_file=key_file, store_dir=store_dir)
    stored = asyncio.run(second_store.get_secret(ref))

    assert stored is not None
    assert stored.get_secret_value() == "oauth-refresh-token"


def test_fernet_store_deletes_secret_file(tmp_path: Path) -> None:
    store = FernetSecretStore(
        key_file=tmp_path / "fernet.key",
        store_dir=tmp_path / "secrets",
    )
    ref = secret_ref()

    asyncio.run(store.set_secret(ref, SecretStr("value-to-delete")))
    assert encrypted_secret_files(tmp_path / "secrets")

    asyncio.run(store.delete_secret(ref))

    assert asyncio.run(store.get_secret(ref)) is None
    assert encrypted_secret_files(tmp_path / "secrets") == []


def test_fernet_store_rejects_invalid_key_file(tmp_path: Path) -> None:
    key_file = tmp_path / "fernet.key"
    key_file.write_bytes(b"not-a-fernet-key")
    store = FernetSecretStore(key_file=key_file, store_dir=tmp_path / "secrets")

    with pytest.raises(SecretStoreUnavailableError):
        asyncio.run(store.set_secret(secret_ref(), SecretStr("secret-value")))


def test_fernet_store_from_settings_uses_configured_key_and_data_dir(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        data_dir=tmp_path / "data",
        fernet_key_file=tmp_path / "keys" / "fernet.key",
    )
    store = FernetSecretStore.from_settings(settings)

    asyncio.run(store.set_secret(secret_ref(), SecretStr("configured-secret")))

    assert (tmp_path / "keys" / "fernet.key").exists()
    encrypted_files = encrypted_secret_files(tmp_path / "data" / "secrets")
    assert len(encrypted_files) == 1
    assert b"configured-secret" not in encrypted_files[0].read_bytes()
