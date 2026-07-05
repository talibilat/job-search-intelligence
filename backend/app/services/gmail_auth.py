from __future__ import annotations

from collections.abc import Callable
from secrets import token_urlsafe

from app.config import AppSettings, EmailProviderName
from app.providers.email import (
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
)
from app.providers.email.gmail import GmailAuthorizationProvider

OAuthStateFactory = Callable[[], str]


def generate_oauth_state() -> str:
    return token_urlsafe(32)


async def start_gmail_authorization(
    *,
    settings: AppSettings,
    redirect_uri: str,
    state_factory: OAuthStateFactory = generate_oauth_state,
) -> EmailAuthorizationStartResult:
    provider = GmailAuthorizationProvider(
        client_config_file=settings.gmail_client_config_file,
        scopes=settings.gmail_scopes,
    )
    return await provider.start_authorization(
        EmailAuthorizationStartRequest(
            provider=EmailProviderName.GMAIL,
            redirect_uri=redirect_uri,
            state=state_factory(),
        )
    )
