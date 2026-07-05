from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.providers.email import EmailAuthorizationStartResult, EmailProviderAuthError
from app.services.gmail_auth import (
    OAuthStateFactory,
    generate_oauth_state,
    start_gmail_authorization,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_oauth_state_factory() -> OAuthStateFactory:
    return generate_oauth_state


@router.get(
    "/gmail",
    response_model=EmailAuthorizationStartResult,
    responses={400: {"model": ApiErrorResponse}},
)
async def gmail_auth_url(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
    state_factory: Annotated[OAuthStateFactory, Depends(get_oauth_state_factory)],
) -> EmailAuthorizationStartResult:
    redirect_uri = f"{str(request.base_url).rstrip('/')}/auth/gmail/callback"
    try:
        return await start_gmail_authorization(
            settings=settings,
            redirect_uri=redirect_uri,
            state_factory=state_factory,
        )
    except EmailProviderAuthError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.public_message,
        ) from error
