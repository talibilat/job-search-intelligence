"""Package-level security interfaces, adapters, and redaction helpers."""

from .factory import build_secret_store
from .fernet_secret_store import FernetSecretStore
from .keyring_store import KeyringBackend, KeyringSecretStore, create_secret_store
from .redaction import (
    EMAIL_CONTENT_REDACTED,
    REDACTED,
    RedactingFilter,
    redact_mapping,
    redact_text,
    redact_value,
)
from .secret_store import (
    SecretKind,
    SecretRef,
    SecretStore,
    SecretStoreError,
    SecretStoreUnavailableError,
)

__all__ = [
    "EMAIL_CONTENT_REDACTED",
    "FernetSecretStore",
    "KeyringBackend",
    "KeyringSecretStore",
    "REDACTED",
    "RedactingFilter",
    "SecretKind",
    "SecretRef",
    "SecretStore",
    "SecretStoreError",
    "SecretStoreUnavailableError",
    "build_secret_store",
    "create_secret_store",
    "redact_mapping",
    "redact_text",
    "redact_value",
]
