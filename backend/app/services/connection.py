from __future__ import annotations

from typing import Protocol

from app.providers.email import EmailAccountRef, EmailConnection
from app.security import SecretStore


class ConnectionRepository(Protocol):
    def fetch_connection_metadata(self, account: EmailAccountRef) -> EmailConnection | None: ...

    def delete_connection(self, account: EmailAccountRef) -> EmailConnection | None: ...


class ConnectionNotFoundError(LookupError):
    """Raised when a requested email connection does not exist."""


class ConnectionDisconnectService:
    """Remove connection credentials and then their retry metadata."""

    def __init__(
        self,
        *,
        connection_repository: ConnectionRepository,
        secret_store: SecretStore,
    ) -> None:
        self._connection_repository = connection_repository
        self._secret_store = secret_store

    async def disconnect(self, account: EmailAccountRef) -> EmailConnection:
        connection = self._connection_repository.fetch_connection_metadata(account)
        if connection is None:
            raise ConnectionNotFoundError

        await self._secret_store.delete_secret(connection.credential_ref)
        deleted = self._connection_repository.delete_connection(account)
        if deleted is None:
            raise ConnectionNotFoundError
        return deleted
