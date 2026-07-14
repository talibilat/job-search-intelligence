from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr

_SECRET_REF_PATTERN = r"^[a-z0-9][a-z0-9_.:-]*$"


class SecretKind(StrEnum):
    OAUTH_TOKEN = "oauth_token"
    OAUTH_CLIENT = "oauth_client"
    LLM_API_KEY = "llm_api_key"


class SecretRef(BaseModel):
    """Stable non-secret identifier for a stored secret."""

    model_config = ConfigDict(frozen=True)

    kind: SecretKind
    provider: str = Field(
        min_length=1,
        max_length=100,
        pattern=_SECRET_REF_PATTERN,
    )
    name: str = Field(
        min_length=1,
        max_length=100,
        pattern=_SECRET_REF_PATTERN,
    )


class SecretStoreError(RuntimeError):
    """Base error for secret-store failures."""


class SecretStoreUnavailableError(SecretStoreError):
    """Raised when the configured secret-store adapter cannot be used."""


@runtime_checkable
class SecretStore(Protocol):
    """Adapter seam for encrypted-at-rest OAuth token and LLM key storage."""

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        """Return a secret value, or None if the ref has no stored secret."""
        ...

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        """Store or replace a secret value encrypted at rest."""
        ...

    async def delete_secret(self, ref: SecretRef) -> None:
        """Delete a stored secret if present."""
        ...
