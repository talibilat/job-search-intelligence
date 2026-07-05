from __future__ import annotations

from collections.abc import Callable
from secrets import token_urlsafe
from typing import Protocol

from pydantic import SecretStr

from app.config import EmailProviderName
from app.providers.email import (
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailConnection,
    EmailProvider,
)

OAuthStateFactory = Callable[[], str]


class OAuthStateStore(Protocol):
    def save_state(self, state: str) -> None: ...

    def consume_state(self, state: str) -> bool: ...


class EmailConnectionWriter(Protocol):
    def save_connection(self, connection: EmailConnection) -> object: ...


class InvalidOAuthStateError(RuntimeError):
    public_message = "Gmail authorization state is invalid or expired."


class InMemoryOAuthStateStore:
    def __init__(self) -> None:
        self._pending_states: set[str] = set()

    def save_state(self, state: str) -> None:
        self._pending_states.add(state)

    def consume_state(self, state: str) -> bool:
        if state not in self._pending_states:
            return False
        self._pending_states.remove(state)
        return True


def generate_oauth_state() -> str:
    return token_urlsafe(32)


async def start_gmail_authorization(
    *,
    email_provider: EmailProvider,
    redirect_uri: str,
    state_store: OAuthStateStore,
    state_factory: OAuthStateFactory = generate_oauth_state,
) -> EmailAuthorizationStartResult:
    state = state_factory()
    authorization = await email_provider.start_authorization(
        EmailAuthorizationStartRequest(
            provider=EmailProviderName.GMAIL,
            redirect_uri=redirect_uri,
            state=state,
        )
    )
    state_store.save_state(authorization.state)
    return authorization


async def complete_gmail_authorization(
    *,
    email_provider: EmailProvider,
    redirect_uri: str,
    state: str,
    code: SecretStr,
    state_store: OAuthStateStore,
    connection_repository: EmailConnectionWriter,
) -> EmailConnection:
    if not state_store.consume_state(state):
        raise InvalidOAuthStateError

    connection = await email_provider.complete_authorization(
        EmailAuthorizationCallbackRequest(
            provider=EmailProviderName.GMAIL,
            redirect_uri=redirect_uri,
            state=state,
            code=code,
        )
    )
    connection_repository.save_connection(connection)
    return connection
