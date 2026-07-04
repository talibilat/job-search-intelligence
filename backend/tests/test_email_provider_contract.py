from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from app.config import GMAIL_READONLY_SCOPE, EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailBodyBatch,
    EmailBodyFetchRequest,
    EmailBodySource,
    EmailConnection,
    EmailMessageBody,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProvider,
    EmailProviderAuthError,
    EmailProviderCapabilities,
    EmailProviderCursor,
    EmailProviderError,
    EmailProviderTransientError,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef
from pydantic import ValidationError

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


class FakeEmailProvider:
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

    async def start_authorization(
        self,
        request: EmailAuthorizationStartRequest,
    ) -> EmailAuthorizationStartResult:
        return EmailAuthorizationStartResult(
            provider=request.provider,
            authorization_url=(
                f"https://accounts.google.com/o/oauth2/v2/auth?state={request.state}"
            ),
            state=request.state,
            requested_scopes=self.capabilities.required_scopes,
        )

    async def complete_authorization(
        self,
        request: EmailAuthorizationCallbackRequest,
    ) -> EmailConnection:
        account = EmailAccountRef(
            provider=request.provider,
            account_id="me@example.com",
        )
        return EmailConnection(
            account=account,
            display_email=EmailAddress(address="me@example.com"),
            credential_ref=SecretRef(
                kind=SecretKind.OAUTH_TOKEN,
                provider=request.provider.value,
                name="me-example-com",
            ),
            granted_scopes=(GMAIL_READONLY_SCOPE,),
            connected_at=NOW,
            credential_expires_at=NOW + timedelta(hours=1),
        )

    async def refresh_connection(self, connection: EmailConnection) -> EmailConnection:
        return connection.model_copy(update={"credential_expires_at": NOW + timedelta(hours=2)})

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        cursor_value = "history-101" if request.mode is EmailSyncMode.INCREMENTAL else "history-1"
        message_ref = EmailMessageRef(
            account=connection.account,
            message_id="msg-1",
            thread_id="thread-1",
        )
        return EmailMetadataPage(
            messages=(
                EmailMessageMetadata(
                    ref=message_ref,
                    rfc822_message_id="<msg-1@example.com>",
                    from_addr=EmailAddress(address="jobs@example.com"),
                    to_addrs=(EmailAddress(address=connection.account.account_id),),
                    cc_addrs=(),
                    subject="Application received",
                    snippet="Thanks for applying.",
                    sent_at=NOW,
                    received_at=NOW,
                    labels=("INBOX",),
                    has_attachments=True,
                    size_bytes=2048,
                ),
            ),
            next_page_token=None,
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value=cursor_value,
                issued_at=NOW,
            ),
        )

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        return EmailBodyBatch(
            bodies=(
                EmailMessageBody(
                    ref=request.refs[0],
                    body_text="Thanks for applying.",
                    body_source=EmailBodySource.TEXT_PLAIN,
                    truncated=False,
                    fetched_at=NOW,
                ),
            ),
            failures=(),
        )


async def _connect_fake_provider(provider: FakeEmailProvider) -> EmailConnection:
    callback_request = EmailAuthorizationCallbackRequest(
        provider=EmailProviderName.GMAIL,
        redirect_uri="http://127.0.0.1:8000/auth/gmail/callback",
        state="csrf-state",
        code="authorization-code",
    )
    return await provider.complete_authorization(callback_request)


def test_fake_email_provider_satisfies_protocol() -> None:
    assert isinstance(FakeEmailProvider(), EmailProvider)


def test_authorization_contract_uses_secret_refs_not_raw_tokens() -> None:
    provider = FakeEmailProvider()

    auth_start = asyncio.run(
        provider.start_authorization(
            EmailAuthorizationStartRequest(
                provider=EmailProviderName.GMAIL,
                redirect_uri="http://127.0.0.1:8000/auth/gmail/callback",
                state="csrf-state",
            )
        )
    )
    connection = asyncio.run(_connect_fake_provider(provider))

    assert auth_start.requested_scopes == (GMAIL_READONLY_SCOPE,)
    assert connection.credential_ref.kind is SecretKind.OAUTH_TOKEN
    assert connection.credential_ref.provider == "gmail"
    assert connection.account.provider is EmailProviderName.GMAIL
    assert not hasattr(connection, "access_token")
    assert not hasattr(connection, "refresh_token")


def test_metadata_contract_supports_full_backfill_and_incremental_cursors() -> None:
    provider = FakeEmailProvider()
    connection = asyncio.run(_connect_fake_provider(provider))

    full_page = asyncio.run(
        provider.list_message_metadata(
            connection,
            EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=500),
        )
    )
    incremental_page = asyncio.run(
        provider.list_message_metadata(
            connection,
            EmailMetadataListRequest(
                mode=EmailSyncMode.INCREMENTAL,
                page_size=500,
                sync_cursor=full_page.next_sync_cursor,
            ),
        )
    )

    assert full_page.messages[0].ref.account.provider is EmailProviderName.GMAIL
    assert full_page.messages[0].body_text is None
    assert full_page.next_sync_cursor is not None
    assert full_page.next_sync_cursor.value == "history-1"
    assert incremental_page.next_sync_cursor is not None
    assert incremental_page.next_sync_cursor.value == "history-101"


def test_body_contract_fetches_candidate_refs_without_attachment_content() -> None:
    provider = FakeEmailProvider()
    connection = asyncio.run(_connect_fake_provider(provider))
    message_ref = EmailMessageRef(
        account=connection.account,
        message_id="msg-1",
        thread_id="thread-1",
    )

    body_batch = asyncio.run(
        provider.fetch_message_bodies(
            connection,
            EmailBodyFetchRequest(refs=(message_ref,), max_body_bytes=10_000),
        )
    )

    assert provider.capabilities.attachment_policy is EmailAttachmentPolicy.IGNORED
    assert body_batch.bodies[0].body_text == "Thanks for applying."
    assert body_batch.bodies[0].body_source is EmailBodySource.TEXT_PLAIN
    assert not hasattr(body_batch.bodies[0], "raw_html")
    assert not hasattr(body_batch.bodies[0], "attachments")


def test_email_provider_boundary_dtos_validate_safe_batches() -> None:
    account = EmailAccountRef(
        provider=EmailProviderName.GMAIL,
        account_id="me@example.com",
    )
    message_ref = EmailMessageRef(
        account=account,
        message_id="msg-1",
    )

    with pytest.raises(ValidationError):
        EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=0)

    with pytest.raises(ValidationError):
        EmailBodyFetchRequest(refs=())

    with pytest.raises(ValidationError):
        EmailBodyFetchRequest(refs=(message_ref,), max_body_bytes=0)


def test_email_provider_errors_are_typed() -> None:
    assert isinstance(EmailProviderAuthError("reauth required"), EmailProviderError)
    assert isinstance(
        EmailSyncCursorExpiredError("incremental cursor expired"),
        EmailProviderError,
    )
    assert isinstance(EmailProviderTransientError("rate limited"), EmailProviderError)
