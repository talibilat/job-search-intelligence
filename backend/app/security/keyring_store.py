from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from pydantic import SecretStr

from app.config import AppSettings, SecretStoreBackend
from app.security.secret_store import SecretRef, SecretStore, SecretStoreUnavailableError

KEYRING_SERVICE_NAME = "job-search-intelligence"
_KEYRING_UNAVAILABLE_MESSAGE = "keyring secret store is unavailable"


class KeyringBackend(Protocol):
    """Minimal keyring client surface used by KeyringSecretStore."""

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KeyringSecretStore:
    """SecretStore adapter backed by the host operating system keyring."""

    def __init__(
        self,
        *,
        keyring_backend: KeyringBackend | None = None,
        service_name: str = KEYRING_SERVICE_NAME,
    ) -> None:
        self._keyring = keyring if keyring_backend is None else keyring_backend
        self._service_name = service_name

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        try:
            value = self._keyring.get_password(self._service_name, _keyring_username(ref))
        except KeyringError:
            raise SecretStoreUnavailableError(_KEYRING_UNAVAILABLE_MESSAGE) from None

        if value is None:
            return None

        return SecretStr(value)

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        try:
            self._keyring.set_password(
                self._service_name,
                _keyring_username(ref),
                value.get_secret_value(),
            )
        except KeyringError:
            raise SecretStoreUnavailableError(_KEYRING_UNAVAILABLE_MESSAGE) from None

    async def delete_secret(self, ref: SecretRef) -> None:
        try:
            self._keyring.delete_password(self._service_name, _keyring_username(ref))
        except PasswordDeleteError:
            return
        except KeyringError:
            raise SecretStoreUnavailableError(_KEYRING_UNAVAILABLE_MESSAGE) from None


def create_secret_store(
    settings: AppSettings,
    *,
    keyring_backend: KeyringBackend | None = None,
) -> SecretStore:
    """Create the configured SecretStore adapter without exposing secret values."""

    if settings.secret_store_backend is SecretStoreBackend.KEYRING:
        return KeyringSecretStore(keyring_backend=keyring_backend)

    if settings.secret_store_backend is SecretStoreBackend.FERNET:
        raise SecretStoreUnavailableError(
            "Fernet secret store fallback is not implemented yet; JT-015 owns it."
        )

    raise SecretStoreUnavailableError("unsupported secret store backend")


def _keyring_username(ref: SecretRef) -> str:
    return "/".join(
        (
            _quote_ref_part(ref.kind.value),
            _quote_ref_part(ref.provider),
            _quote_ref_part(ref.name),
        )
    )


def _quote_ref_part(value: str) -> str:
    return quote(value, safe="")
