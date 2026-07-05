from __future__ import annotations

from collections.abc import Callable
from secrets import token_urlsafe

from app.config import EmailProviderName
from app.providers.email import (
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailProvider,
)

OAuthStateFactory = Callable[[], str]


def generate_oauth_state() -> str:
    return token_urlsafe(32)


async def start_gmail_authorization(
    *,
    email_provider: EmailProvider,
    redirect_uri: str,
    state_factory: OAuthStateFactory = generate_oauth_state,
) -> EmailAuthorizationStartResult:
    return await email_provider.start_authorization(
        EmailAuthorizationStartRequest(
            provider=EmailProviderName.GMAIL,
            redirect_uri=redirect_uri,
            state=state_factory(),
        )
    )
