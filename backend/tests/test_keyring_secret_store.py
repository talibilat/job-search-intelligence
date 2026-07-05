from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.config import AppSettings, SecretStoreBackend
from app.security import (
    FernetSecretStore,
    KeyringSecretStore,
    SecretKind,
    SecretRef,
    SecretStore,
    SecretStoreUnavailableError,
    create_secret_store,
)
from keyring.errors import KeyringError, PasswordDeleteError
from pydantic import SecretStr


class FakeKeyringBackend:
    def __init__(self) -> None:
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.passwords.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.passwords[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        if (service_name, username) not in self.passwords:
            raise PasswordDeleteError("not found")
        del self.passwords[(service_name, username)]


class FailingKeyringBackend:
    def __init__(self, raw_secret: str) -> None:
        self.raw_secret = raw_secret

    def get_password(self, service_name: str, username: str) -> str | None:
        raise KeyringError("backend unavailable")

    def set_password(self, service_name: str, username: str, password: str) -> None:
        raise KeyringError(f"backend unavailable for {self.raw_secret}")

    def delete_password(self, service_name: str, username: str) -> None:
        raise KeyringError("backend unavailable")


def llm_api_key_ref() -> SecretRef:
    return SecretRef(
        kind=SecretKind.LLM_API_KEY,
        provider="azure_openai",
        name="api_key",
    )


def test_keyring_store_satisfies_secret_store_protocol() -> None:
    store = KeyringSecretStore(keyring_backend=FakeKeyringBackend())

    assert isinstance(store, SecretStore)


def test_keyring_store_round_trips_secret_values_without_secret_identifiers() -> None:
    backend = FakeKeyringBackend()
    store = KeyringSecretStore(keyring_backend=backend)
    ref = llm_api_key_ref()
    raw_secret = "provider-api-key"

    async def exercise_store() -> None:
        assert await store.get_secret(ref) is None

        await store.set_secret(ref, SecretStr(raw_secret))

        stored_secret = await store.get_secret(ref)
        assert stored_secret is not None
        assert stored_secret.get_secret_value() == raw_secret

    asyncio.run(exercise_store())

    assert len(backend.passwords) == 1
    [(service_name, username)] = backend.passwords.keys()
    assert raw_secret not in service_name
    assert raw_secret not in username
    assert "azure_openai" in username
    assert "api_key" in username


def test_keyring_store_delete_is_idempotent() -> None:
    backend = FakeKeyringBackend()
    store = KeyringSecretStore(keyring_backend=backend)
    ref = llm_api_key_ref()

    async def exercise_store() -> None:
        await store.set_secret(ref, SecretStr("provider-api-key"))
        await store.delete_secret(ref)
        await store.delete_secret(ref)

        assert await store.get_secret(ref) is None

    asyncio.run(exercise_store())


def test_keyring_store_translates_backend_errors_without_secret_values() -> None:
    raw_secret = "provider-api-key"
    store = KeyringSecretStore(keyring_backend=FailingKeyringBackend(raw_secret))

    async def exercise_store() -> None:
        with pytest.raises(SecretStoreUnavailableError) as error_info:
            await store.set_secret(llm_api_key_ref(), SecretStr(raw_secret))

        assert raw_secret not in str(error_info.value)
        assert error_info.value.__cause__ is None

    asyncio.run(exercise_store())


def test_create_secret_store_uses_keyring_by_default() -> None:
    store = create_secret_store(
        AppSettings(_env_file=None),
        keyring_backend=FakeKeyringBackend(),
    )

    assert isinstance(store, KeyringSecretStore)


def test_create_secret_store_uses_fernet_fallback(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        secret_store_backend=SecretStoreBackend.FERNET,
        data_dir=tmp_path / "data",
        fernet_key_file=tmp_path / "keys" / "fernet.key",
    )

    store = create_secret_store(settings, keyring_backend=FakeKeyringBackend())

    assert isinstance(store, FernetSecretStore)
