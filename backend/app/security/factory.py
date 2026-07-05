from __future__ import annotations

from app.config import AppSettings, SecretStoreBackend
from app.security.keyring_store import create_secret_store
from app.security.secret_store import SecretStore, SecretStoreUnavailableError


def build_secret_store(settings: AppSettings) -> SecretStore:
    if settings.secret_store_backend in {SecretStoreBackend.KEYRING, SecretStoreBackend.FERNET}:
        return create_secret_store(settings)

    raise SecretStoreUnavailableError("unsupported secret store backend")
