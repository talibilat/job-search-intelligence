"""Package-level security interfaces, adapters, and redaction helpers."""

from .factory import build_secret_store
from .fernet_secret_store import FernetSecretStore
from .keyring_store import KeyringSecretStore, create_secret_store
from .provider_refs import AZURE_OPENAI_API_KEY_REF, GMAIL_OAUTH_CLIENT_REF, TAVILY_API_KEY_REF
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
    "AZURE_OPENAI_API_KEY_REF",
    "FernetSecretStore",
    "KeyringSecretStore",
    "GMAIL_OAUTH_CLIENT_REF",
    "REDACTED",
    "RedactingFilter",
    "SecretKind",
    "SecretRef",
    "SecretStore",
    "SecretStoreError",
    "SecretStoreUnavailableError",
    "TAVILY_API_KEY_REF",
    "build_secret_store",
    "create_secret_store",
    "redact_mapping",
    "redact_text",
    "redact_value",
]
