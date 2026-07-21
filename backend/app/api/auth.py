from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import SecretStr

from app.api.dependencies import (
    get_email_connection_repository as get_email_connection_repository,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, EmailProviderName, get_settings
from app.db.repositories.connection import EmailConnectionRepository
from app.db.repositories.oauth_state import OAuthStateRepository
from app.db.sqlite_url import sqlite_database_path
from app.providers.email import (
    EmailAccountRef,
    EmailAuthorizationStartResult,
    EmailConnection,
    EmailProvider,
    EmailProviderAuthError,
    EmailProviderError,
    EmailProviderTransientError,
)
from app.providers.email.gmail import GmailEmailProvider
from app.security import SecretStore, SecretStoreError, create_secret_store
from app.services.connection import ConnectionDisconnectService, ConnectionNotFoundError
from app.services.gmail_auth import (
    InMemoryOAuthStateStore,
    InvalidOAuthStateError,
    OAuthStateFactory,
    OAuthStateStore,
    SQLiteOAuthStateStore,
    complete_gmail_authorization,
    generate_oauth_state,
    start_gmail_authorization,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_oauth_state_factory() -> OAuthStateFactory:
    return generate_oauth_state


def get_oauth_state_store(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[OAuthStateStore]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        try:
            connection.execute("SELECT 1 FROM oauth_authorization_states LIMIT 1")
        except sqlite3.OperationalError as error:
            if "no such table: oauth_authorization_states" not in str(error):
                raise
            yield InMemoryOAuthStateStore()
        else:
            yield SQLiteOAuthStateStore(OAuthStateRepository(connection))
    finally:
        connection.close()


def get_gmail_secret_store(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SecretStore:
    return create_secret_store(settings)


def get_gmail_email_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
    secret_store: Annotated[SecretStore, Depends(get_gmail_secret_store)],
) -> EmailProvider:
    return GmailEmailProvider(settings=settings, secret_store=secret_store)


@router.get(
    "/connections",
    response_model=list[EmailConnection],
    summary="List Email Connections",
    description=(
        "Returns non-secret metadata for every locally stored email connection. "
        "Token material never leaves the configured secret store."
    ),
)
def list_email_connections(
    connection_repository: Annotated[
        EmailConnectionRepository,
        Depends(get_email_connection_repository),
    ],
) -> list[EmailConnection]:
    return connection_repository.list_connections_metadata()


@router.delete(
    "/connections/{provider}/{account_id}",
    response_model=EmailConnection,
    responses={
        404: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    summary="Disconnect Email Connection",
    description=(
        "Removes one stored email connection and deletes its credential from the "
        "configured secret store. Provider-side mailbox data is never touched."
    ),
)
async def disconnect_email_connection(
    provider: EmailProviderName,
    account_id: str,
    connection_repository: Annotated[
        EmailConnectionRepository,
        Depends(get_email_connection_repository),
    ],
    secret_store: Annotated[SecretStore, Depends(get_gmail_secret_store)],
) -> EmailConnection:
    account = EmailAccountRef(provider=provider, account_id=account_id)
    try:
        return await ConnectionDisconnectService(
            connection_repository=connection_repository,
            secret_store=secret_store,
        ).disconnect(account)
    except ConnectionNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Email connection not found.",
        ) from error
    except SecretStoreError as error:
        raise ApiError(
            status_code=503,
            code=ApiErrorCode.SERVICE_UNAVAILABLE,
            message="Stored credentials could not be removed. Try again.",
        ) from error


@router.get(
    "/gmail",
    response_model=EmailAuthorizationStartResult,
    responses={400: {"model": ApiErrorResponse}},
)
async def gmail_auth_url(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_provider: Annotated[EmailProvider, Depends(get_gmail_email_provider)],
    state_factory: Annotated[OAuthStateFactory, Depends(get_oauth_state_factory)],
    state_store: Annotated[OAuthStateStore, Depends(get_oauth_state_store)],
) -> EmailAuthorizationStartResult:
    redirect_uri = _gmail_redirect_uri(request, settings)
    try:
        return await start_gmail_authorization(
            email_provider=email_provider,
            redirect_uri=redirect_uri,
            state_store=state_store,
            state_factory=state_factory,
        )
    except EmailProviderAuthError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.public_message,
        ) from error


@router.get(
    "/gmail/callback",
    response_model=EmailConnection,
    responses={400: {"model": ApiErrorResponse}},
)
async def gmail_auth_callback(
    request: Request,
    code: Annotated[SecretStr, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    email_provider: Annotated[EmailProvider, Depends(get_gmail_email_provider)],
    settings: Annotated[AppSettings, Depends(get_settings)],
    state_store: Annotated[OAuthStateStore, Depends(get_oauth_state_store)],
    connection_repository: Annotated[
        EmailConnectionRepository,
        Depends(get_email_connection_repository),
    ],
) -> RedirectResponse:
    redirect_uri = _gmail_redirect_uri(request, settings)
    try:
        await complete_gmail_authorization(
            email_provider=email_provider,
            redirect_uri=redirect_uri,
            state=state,
            code=code,
            state_store=state_store,
            connection_repository=connection_repository,
        )
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/settings?gmail=connected",
            status_code=303,
        )
    except InvalidOAuthStateError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.public_message,
        ) from error
    except EmailProviderAuthError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.public_message,
        ) from error
    except EmailProviderTransientError as error:
        raise ApiError(
            status_code=503,
            code=ApiErrorCode.SERVICE_UNAVAILABLE,
            message=error.public_message,
        ) from error
    except EmailProviderError as error:
        raise ApiError(
            status_code=502,
            code=ApiErrorCode.BAD_GATEWAY,
            message=error.public_message,
        ) from error


def _gmail_redirect_uri(request: Request, settings: AppSettings) -> str:
    """Use an explicit host URL when a reverse proxy hides the public callback host."""

    base_url = settings.api_public_url or str(request.base_url)
    return f"{base_url.rstrip('/')}/auth/gmail/callback"
