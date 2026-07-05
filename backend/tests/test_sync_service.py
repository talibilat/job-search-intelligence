from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import GMAIL_READONLY_SCOPE, EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailConnection,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCapabilities,
    EmailProviderCursor,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef
from app.services.sync_service import EmailSyncService

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class ExpiringHistoryProvider:
    name = EmailProviderName.GMAIL
    capabilities = EmailProviderCapabilities(
        provider=EmailProviderName.GMAIL,
        required_scopes=(GMAIL_READONLY_SCOPE,),
        supports_oauth=True,
        supports_full_backfill=True,
        supports_incremental_sync=True,
        attachment_policy=EmailAttachmentPolicy.IGNORED,
        max_metadata_page_size=500,
        max_body_batch_size=100,
    )

    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        if request.mode is EmailSyncMode.INCREMENTAL:
            raise EmailSyncCursorExpiredError(public_message="history cursor expired")

        return EmailMetadataPage(
            messages=(
                EmailMessageMetadata(
                    ref=EmailMessageRef(
                        account=connection.account,
                        message_id="msg-reconciled",
                        thread_id="thread-reconciled",
                    ),
                    from_addr=EmailAddress(address="jobs@example.com"),
                    subject="Application received",
                    received_at=NOW,
                ),
            ),
            next_page_token="page-2",
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-recovered",
                issued_at=NOW,
            ),
        )


class RecordingHistoryProvider:
    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        return EmailMetadataPage(
            messages=(),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-next",
                issued_at=NOW,
            ),
        )


def test_expired_history_id_falls_back_to_resumable_reconciliation() -> None:
    provider = ExpiringHistoryProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    expired_cursor = EmailProviderCursor(
        account=connection.account,
        value="history-expired",
        issued_at=NOW - timedelta(days=30),
    )

    result = asyncio.run(
        service.list_metadata_page(
            connection=connection,
            sync_cursor=expired_cursor,
        )
    )

    assert result.recovered_from_expired_cursor is True
    assert result.mode is EmailSyncMode.FULL_BACKFILL
    assert result.page.next_page_token == "page-2"
    assert result.page.next_sync_cursor is not None
    assert result.page.next_sync_cursor.value == "history-recovered"
    assert [request.mode for request in provider.requests] == [
        EmailSyncMode.INCREMENTAL,
        EmailSyncMode.FULL_BACKFILL,
    ]
    assert provider.requests[0].sync_cursor == expired_cursor
    assert provider.requests[1].sync_cursor is None
    assert provider.requests[1].page_size == 250


def test_incremental_metadata_page_forwards_resume_page_token() -> None:
    provider = RecordingHistoryProvider()
    service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()
    cursor = EmailProviderCursor(
        account=connection.account,
        value="history-current",
        issued_at=NOW,
    )

    result = asyncio.run(
        service.list_metadata_page(
            connection=connection,
            sync_cursor=cursor,
            page_token="incremental-page-2",
        )
    )

    assert result.recovered_from_expired_cursor is False
    assert result.mode is EmailSyncMode.INCREMENTAL
    assert len(provider.requests) == 1
    assert provider.requests[0].mode is EmailSyncMode.INCREMENTAL
    assert provider.requests[0].sync_cursor == cursor
    assert provider.requests[0].page_token == "incremental-page-2"


def email_connection() -> EmailConnection:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailConnection(
        account=account,
        display_email=EmailAddress(address="me@example.com"),
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=NOW,
    )
