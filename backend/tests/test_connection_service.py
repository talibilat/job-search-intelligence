from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from app.config import EmailProviderName
from app.providers.email import EmailAccountRef, EmailConnection
from app.security import SecretKind, SecretRef, SecretStoreUnavailableError
from app.services.connection import ConnectionDisconnectService
from pydantic import SecretStr


def connection() -> EmailConnection:
    return EmailConnection(
        account=EmailAccountRef(
            provider=EmailProviderName.GMAIL,
            account_id="me@example.com",
        ),
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        connected_at=datetime(2026, 7, 12, tzinfo=UTC),
    )


class RecordingRepository:
    def __init__(self, stored: EmailConnection) -> None:
        self.stored = stored
        self.deleted = False

    def fetch_connection_metadata(self, account: EmailAccountRef) -> EmailConnection | None:
        return None if self.deleted or account != self.stored.account else self.stored

    def delete_connection(self, account: EmailAccountRef) -> EmailConnection | None:
        if account != self.stored.account:
            return None
        self.deleted = True
        return self.stored


class RecordingSecretStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[SecretRef] = []

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        del ref
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        if self.fail:
            raise SecretStoreUnavailableError("private adapter failure")
        self.deleted.append(ref)


def test_disconnect_keeps_connection_metadata_when_secret_deletion_fails() -> None:
    stored = connection()
    repository = RecordingRepository(stored)
    service = ConnectionDisconnectService(
        connection_repository=repository,
        secret_store=RecordingSecretStore(fail=True),
    )

    with pytest.raises(SecretStoreUnavailableError):
        asyncio.run(service.disconnect(stored.account))

    assert repository.fetch_connection_metadata(stored.account) == stored


def test_disconnect_deletes_secret_before_connection_metadata() -> None:
    stored = connection()
    repository = RecordingRepository(stored)
    secret_store = RecordingSecretStore()
    service = ConnectionDisconnectService(
        connection_repository=repository,
        secret_store=secret_store,
    )

    result = asyncio.run(service.disconnect(stored.account))

    assert result == stored
    assert secret_store.deleted == [stored.credential_ref]
    assert repository.fetch_connection_metadata(stored.account) is None
