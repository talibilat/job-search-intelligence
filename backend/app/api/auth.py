from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import SecretStr

from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.providers.email import (
    EmailAuthorizationStartResult,
    EmailConnection,
    EmailProvider,
    EmailProviderAuthError,
)
from app.providers.email.gmail import GmailEmailProvider
from app.security import SecretStore, create_secret_store
from app.services.gmail_auth import (
    OAuthStateFactory,
    complete_gmail_authorization,
    generate_oauth_state,
    start_gmail_authorization,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_oauth_state_factory() -> OAuthStateFactory:
    return generate_oauth_state


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
    "/gmail",
    response_model=EmailAuthorizationStartResult,
    responses={400: {"model": ApiErrorResponse}},
)
async def gmail_auth_url(
    request: Request,
    email_provider: Annotated[EmailProvider, Depends(get_gmail_email_provider)],
    state_factory: Annotated[OAuthStateFactory, Depends(get_oauth_state_factory)],
) -> EmailAuthorizationStartResult:
    redirect_uri = f"{str(request.base_url).rstrip('/')}/auth/gmail/callback"
    try:
        return await start_gmail_authorization(
            email_provider=email_provider,
            redirect_uri=redirect_uri,
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
) -> EmailConnection:
    redirect_uri = f"{str(request.base_url).rstrip('/')}/auth/gmail/callback"
    try:
        return await complete_gmail_authorization(
            email_provider=email_provider,
            redirect_uri=redirect_uri,
            state=state,
            code=code,
        )
    except EmailProviderAuthError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.public_message,
        ) from error
