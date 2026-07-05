from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailBodyFetchRequest,
    EmailConnection,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailProvider,
    EmailProviderError,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef
from pydantic import SecretStr

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def _settings() -> AppSettings:
    return AppSettings(_env_file=None, gmail_page_size=250)


def _gmail_provider(settings: AppSettings) -> EmailProvider:
    from app.providers.email.gmail import GmailEmailProvider

    return GmailEmailProvider(settings=settings)


def _connection() -> EmailConnection:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailConnection(
        account=account,
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=NOW,
    )


def test_gmail_email_provider_satisfies_email_provider_protocol() -> None:
    provider = _gmail_provider(_settings())

    assert isinstance(provider, EmailProvider)
    assert provider.name is EmailProviderName.GMAIL
    assert provider.capabilities.provider is EmailProviderName.GMAIL
    assert provider.capabilities.required_scopes == (GMAIL_READONLY_SCOPE,)
    assert provider.capabilities.supports_oauth is True
    assert provider.capabilities.supports_full_backfill is True
    assert provider.capabilities.supports_incremental_sync is True
    assert provider.capabilities.attachment_policy is EmailAttachmentPolicy.IGNORED
    assert provider.capabilities.max_metadata_page_size == 250


def test_gmail_email_provider_rejects_non_readonly_scope_configuration() -> None:
    settings = AppSettings.model_construct(
        email_provider=EmailProviderName.GMAIL,
        gmail_scopes=(GMAIL_READONLY_SCOPE, "https://www.googleapis.com/auth/gmail.modify"),
        gmail_page_size=500,
    )

    with pytest.raises(EmailProviderError, match="gmail.readonly"):
        _gmail_provider(settings)


def test_gmail_email_provider_skeleton_raises_public_safe_errors() -> None:
    provider = _gmail_provider(_settings())

    callback_request = EmailAuthorizationCallbackRequest(
        provider=EmailProviderName.GMAIL,
        redirect_uri="http://127.0.0.1:8000/auth/gmail/callback",
        state="csrf-state",
        code=SecretStr("authorization-code"),
    )
    connection = _connection()
    metadata_request = EmailMetadataListRequest(
        mode=EmailSyncMode.FULL_BACKFILL,
        page_size=250,
    )
    body_request = EmailBodyFetchRequest(
        refs=(EmailMessageRef(account=connection.account, message_id="msg-1"),),
    )

    operations = (
        provider.complete_authorization(callback_request),
        provider.refresh_connection(connection),
        provider.list_message_metadata(connection, metadata_request),
        provider.fetch_message_bodies(connection, body_request),
    )

    for operation in operations:
        with pytest.raises(EmailProviderError) as error_info:
            asyncio.run(operation)

        assert error_info.value.public_message.endswith("not implemented yet.")
        assert "authorization-code" not in str(error_info.value)
        assert "csrf-state" not in str(error_info.value)
        assert "me@example.com" not in str(error_info.value)
