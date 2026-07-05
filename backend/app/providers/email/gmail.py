from __future__ import annotations

from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName
from app.providers.email.provider import (
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailBodyBatch,
    EmailBodyFetchRequest,
    EmailConnection,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCapabilities,
    EmailProviderError,
)

_GMAIL_RUNTIME_NOT_IMPLEMENTED = "Gmail provider runtime is not implemented yet."
_GMAIL_MAX_BODY_BATCH_SIZE = 100


class GmailEmailProvider:
    """Gmail `EmailProvider` skeleton for Phase 1 ingestion work."""

    name = EmailProviderName.GMAIL

    def __init__(self, *, settings: AppSettings) -> None:
        if tuple(settings.gmail_scopes) != (GMAIL_READONLY_SCOPE,):
            raise EmailProviderError(
                public_message="Gmail provider requires only the gmail.readonly scope."
            )

        self.capabilities = EmailProviderCapabilities(
            provider=EmailProviderName.GMAIL,
            required_scopes=(GMAIL_READONLY_SCOPE,),
            supports_oauth=True,
            supports_full_backfill=True,
            supports_incremental_sync=True,
            attachment_policy=EmailAttachmentPolicy.IGNORED,
            max_metadata_page_size=settings.gmail_page_size,
            max_body_batch_size=_GMAIL_MAX_BODY_BATCH_SIZE,
        )

    async def start_authorization(
        self,
        request: EmailAuthorizationStartRequest,
    ) -> EmailAuthorizationStartResult:
        raise _gmail_runtime_not_implemented()

    async def complete_authorization(
        self,
        request: EmailAuthorizationCallbackRequest,
    ) -> EmailConnection:
        raise _gmail_runtime_not_implemented()

    async def refresh_connection(self, connection: EmailConnection) -> EmailConnection:
        raise _gmail_runtime_not_implemented()

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        raise _gmail_runtime_not_implemented()

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        raise _gmail_runtime_not_implemented()


def _gmail_runtime_not_implemented() -> EmailProviderError:
    return EmailProviderError(public_message=_GMAIL_RUNTIME_NOT_IMPLEMENTED)
