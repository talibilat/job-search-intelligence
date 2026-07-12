from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import SecretStr

from app.api.dependencies import (
    get_email_connection_repository as get_email_connection_repository,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, EmailProviderName, get_settings
from app.db.repositories.connection import EmailConnectionRepository
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
    complete_gmail_authorization,
    generate_oauth_state,
    start_gmail_authorization,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_oauth_state_factory() -> OAuthStateFactory:
    return generate_oauth_state


def get_oauth_state_store(request: Request) -> OAuthStateStore:
    state_store = getattr(request.app.state, "oauth_state_store", None)
    if state_store is None:
        state_store = InMemoryOAuthStateStore()
        request.app.state.oauth_state_store = state_store
    return state_store


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
    email_provider: Annotated[EmailProvider, Depends(get_gmail_email_provider)],
    state_factory: Annotated[OAuthStateFactory, Depends(get_oauth_state_factory)],
    state_store: Annotated[OAuthStateStore, Depends(get_oauth_state_store)],
) -> EmailAuthorizationStartResult:
    redirect_uri = f"{str(request.base_url).rstrip('/')}/auth/gmail/callback"
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
    state_store: Annotated[OAuthStateStore, Depends(get_oauth_state_store)],
    connection_repository: Annotated[
        EmailConnectionRepository,
        Depends(get_email_connection_repository),
    ],
) -> EmailConnection:
    redirect_uri = f"{str(request.base_url).rstrip('/')}/auth/gmail/callback"
    try:
        return await complete_gmail_authorization(
            email_provider=email_provider,
            redirect_uri=redirect_uri,
            state=state,
            code=code,
            state_store=state_store,
            connection_repository=connection_repository,
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
