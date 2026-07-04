from __future__ import annotations

import asyncio

import pytest
from pydantic import SecretStr, ValidationError

from app.security import (
    SecretKind,
    SecretRef,
    SecretStore,
    SecretStoreError,
    SecretStoreUnavailableError,
)


class FakeSecretStore:
    def __init__(self) -> None:
        self._secrets: dict[SecretRef, SecretStr] = {}

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return self._secrets.get(ref)

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        self._secrets[ref] = value

    async def delete_secret(self, ref: SecretRef) -> None:
        self._secrets.pop(ref, None)


async def _round_trip_secret(ref: SecretRef, raw_value: str) -> None:
    store = FakeSecretStore()

    assert await store.get_secret(ref) is None

    await store.set_secret(ref, SecretStr(raw_value))

    stored_value = await store.get_secret(ref)
    assert stored_value is not None
    assert stored_value.get_secret_value() == raw_value

    await store.delete_secret(ref)
    assert await store.get_secret(ref) is None


def test_fake_store_satisfies_secret_store_protocol() -> None:
    assert isinstance(FakeSecretStore(), SecretStore)


def test_secret_store_supports_oauth_token_refs() -> None:
    ref = SecretRef(
        kind=SecretKind.OAUTH_TOKEN,
        provider="gmail",
        name="refresh_token",
    )

    asyncio.run(_round_trip_secret(ref, "oauth-refresh-token"))


def test_secret_store_supports_llm_api_key_refs() -> None:
    ref = SecretRef(
        kind=SecretKind.LLM_API_KEY,
        provider="azure_openai",
        name="api_key",
    )

    asyncio.run(_round_trip_secret(ref, "llm-api-key"))


def test_secret_ref_rejects_blank_secret_names() -> None:
    with pytest.raises(ValidationError):
        SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="",
        )


def test_secret_value_repr_does_not_expose_raw_value() -> None:
    secret = SecretStr("super-secret-token")

    assert "super-secret-token" not in repr(secret)
    assert secret.get_secret_value() == "super-secret-token"


def test_secret_store_unavailable_error_is_typed() -> None:
    error = SecretStoreUnavailableError("secret store is unavailable")

    assert isinstance(error, SecretStoreError)
