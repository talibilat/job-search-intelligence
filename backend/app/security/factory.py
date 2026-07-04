from __future__ import annotations

from app.config import AppSettings, SecretStoreBackend
from app.security.fernet_secret_store import FernetSecretStore
from app.security.secret_store import SecretStore, SecretStoreUnavailableError


def build_secret_store(settings: AppSettings) -> SecretStore:
    if settings.secret_store_backend is SecretStoreBackend.FERNET:
        return FernetSecretStore.from_settings(settings)

    raise SecretStoreUnavailableError("Keyring secret store is not implemented yet.")
