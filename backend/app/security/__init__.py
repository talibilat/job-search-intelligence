"""Security interfaces and adapters."""

from .factory import build_secret_store
from .fernet_secret_store import FernetSecretStore
from .keyring_store import KeyringBackend, KeyringSecretStore, create_secret_store
from .secret_store import (
    SecretKind,
    SecretRef,
    SecretStore,
    SecretStoreError,
    SecretStoreUnavailableError,
)

__all__ = [
    "FernetSecretStore",
    "build_secret_store",
    "KeyringBackend",
    "KeyringSecretStore",
    "SecretKind",
    "SecretRef",
    "SecretStore",
    "SecretStoreError",
    "SecretStoreUnavailableError",
    "create_secret_store",
]
