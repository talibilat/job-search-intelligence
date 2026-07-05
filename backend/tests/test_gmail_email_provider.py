from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest
from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailBodyFetchFailureReason,
    EmailBodyFetchRequest,
    EmailBodySource,
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


class FakeSecretStore:
    def __init__(self, secret: SecretStr | None) -> None:
        self.secret = secret
        self.secrets: dict[SecretRef, SecretStr] = {}

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return self.secrets.get(ref, self.secret)

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        self.secret = value
        self.secrets[ref] = value

    async def delete_secret(self, ref: SecretRef) -> None:
        self.secret = None
        self.secrets.pop(ref, None)


class FakeGmailTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[tuple[str, str], ...], str]] = []

    async def get_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        self.calls.append((path, query, access_token.get_secret_value()))
        if path == "/gmail/v1/users/me/profile":
            return {"historyId": "12345"}

        if path == "/gmail/v1/users/me/messages":
            return {"messages": [{"id": "msg-1", "threadId": "thread-1"}]}

        if path == "/gmail/v1/users/me/messages/msg-1" and dict(query).get("format") == "full":
            return {
                "id": "msg-1",
                "threadId": "thread-1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {
                                "data": _gmail_body_data(
                                    "Thanks for applying to Example Corp.\nNext steps soon."
                                )
                            },
                        },
                        {
                            "filename": "resume.pdf",
                            "mimeType": "application/pdf",
                            "body": {"attachmentId": "attachment-1", "size": 2048},
                        },
                    ],
                },
            }

        if path == "/gmail/v1/users/me/messages/msg-1":
            return {
                "id": "msg-1",
                "threadId": "thread-1",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Jobs <jobs@example.com>"},
                        {"name": "Subject", "value": "Application received"},
                        {"name": "Date", "value": "Sun, 05 Jul 2026 12:00:00 +0000"},
                    ]
                },
                "snippet": "Private body-derived snippet must not be retained.",
                "sizeEstimate": 2048,
            }

        if path == "/gmail/v1/users/me/messages/msg-html":
            return {
                "id": "msg-html",
                "threadId": "thread-html",
                "payload": {
                    "mimeType": "text/html",
                    "body": {
                        "data": _gmail_body_data(
                            "<h1>Application update</h1>"
                            "<p>Please schedule an <strong>interview</strong>.</p>"
                        )
                    },
                },
            }

        if path == "/gmail/v1/users/me/messages/msg-empty":
            return {
                "id": "msg-empty",
                "threadId": "thread-empty",
                "payload": {"mimeType": "text/plain", "body": {}},
            }

        if path == "/gmail/v1/users/me/messages/msg-mislabelled-html":
            return {
                "id": "msg-mislabelled-html",
                "threadId": "thread-mislabelled-html",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {
                        "data": _gmail_body_data(
                            "<p>Sensitive application update from Example Corp.</p>"
                        )
                    },
                },
            }

        if path == "/gmail/v1/users/me/messages/msg-empty-plain-with-html":
            return {
                "id": "msg-empty-plain-with-html",
                "threadId": "thread-empty-plain-with-html",
                "payload": {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _gmail_body_data("")}},
                        {
                            "mimeType": "text/html",
                            "body": {
                                "data": _gmail_body_data(
                                    "<h1>Application update</h1><p>Book an interview.</p>"
                                )
                            },
                        },
                    ],
                },
            }

        if path == "/gmail/v1/users/me/messages/msg-unicode":
            return {
                "id": "msg-unicode",
                "threadId": "thread-unicode",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": _gmail_body_data("éé")},
                },
            }
        raise AssertionError(f"unexpected Gmail path: {path}")


class FakeGmailProfileTransport(FakeGmailTransport):
    async def get_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        self.calls.append((path, query, access_token.get_secret_value()))
        if path == "/gmail/v1/users/me/profile":
            return {"emailAddress": "Me@Example.com"}
        return await super().get_json(path, query=query, access_token=access_token)


class DeletedMessageGmailTransport(FakeGmailTransport):
    async def get_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        if path == "/gmail/v1/users/me/messages/msg-deleted":
            raise HTTPError(path, 404, "not found", hdrs=Message(), fp=None)
        return await super().get_json(path, query=query, access_token=access_token)


class FakeOAuthTokenTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    async def post_form_json(
        self,
        url: str,
        *,
        form: tuple[tuple[str, str], ...],
    ) -> dict[str, object]:
        self.calls.append((url, form))
        return {
            "access_token": "gmail-access-token",
            "refresh_token": "gmail-refresh-token",
            "expires_in": 3600,
            "scope": GMAIL_READONLY_SCOPE,
            "token_type": "Bearer",
        }


def write_google_oauth_client_config(tmp_path: Path) -> Path:
    client_config = tmp_path / "google-oauth-client.json"
    client_config.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "project_id": "jobtracker-local",
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": "super-secret-client-secret",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    return client_config


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


def _gmail_body_data(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


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


def test_gmail_email_provider_remaining_placeholders_raise_public_safe_errors() -> None:
    provider = _gmail_provider(_settings())

    connection = _connection()
    metadata_request = EmailMetadataListRequest(
        mode=EmailSyncMode.FULL_BACKFILL,
        page_size=250,
    )
    body_request = EmailBodyFetchRequest(
        refs=(EmailMessageRef(account=connection.account, message_id="msg-1"),),
    )

    operations = (
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


def test_gmail_email_provider_completes_authorization_and_persists_tokens(
    tmp_path: Path,
) -> None:
    from app.providers.email.gmail import GmailEmailProvider

    secret_store = FakeSecretStore(None)
    token_transport = FakeOAuthTokenTransport()
    gmail_transport = FakeGmailProfileTransport()
    provider = GmailEmailProvider(
        settings=AppSettings(
            _env_file=None,
            gmail_client_config_file=write_google_oauth_client_config(tmp_path),
        ),
        secret_store=secret_store,
        transport=gmail_transport,
        token_transport=token_transport,
    )

    connection = asyncio.run(
        provider.complete_authorization(
            EmailAuthorizationCallbackRequest(
                provider=EmailProviderName.GMAIL,
                redirect_uri="http://127.0.0.1:8000/auth/gmail/callback",
                state="csrf-state",
                code=SecretStr("authorization-code"),
            )
        )
    )

    assert connection.account.account_id == "me@example.com"
    assert connection.display_email is not None
    assert connection.display_email.address == "me@example.com"
    assert connection.credential_ref.kind is SecretKind.OAUTH_TOKEN
    assert connection.credential_ref.provider == "gmail"
    assert "@" not in connection.credential_ref.name
    assert connection.granted_scopes == (GMAIL_READONLY_SCOPE,)
    assert connection.credential_expires_at is not None
    assert connection.credential_expires_at > connection.connected_at
    assert "authorization-code" not in connection.model_dump_json()
    assert "gmail-access-token" not in connection.model_dump_json()
    assert "gmail-refresh-token" not in connection.model_dump_json()

    stored_secret = secret_store.secrets[connection.credential_ref]
    stored_payload = json.loads(stored_secret.get_secret_value())
    assert stored_payload["access_token"] == "gmail-access-token"
    assert stored_payload["refresh_token"] == "gmail-refresh-token"
    assert stored_payload["scope"] == GMAIL_READONLY_SCOPE

    assert token_transport.calls == [
        (
            "https://oauth2.googleapis.com/token",
            (
                ("client_id", "client-id.apps.googleusercontent.com"),
                ("client_secret", "super-secret-client-secret"),
                ("code", "authorization-code"),
                ("grant_type", "authorization_code"),
                ("redirect_uri", "http://127.0.0.1:8000/auth/gmail/callback"),
            ),
        )
    ]
    assert gmail_transport.calls == [
        (
            "/gmail/v1/users/me/profile",
            (("fields", "emailAddress"),),
            "gmail-access-token",
        )
    ]


def test_gmail_email_provider_lists_message_metadata_with_configured_secret_store() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    transport = FakeGmailTransport()
    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )

    page = asyncio.run(
        provider.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=50),
        )
    )

    assert len(page.messages) == 1
    message = page.messages[0]
    assert message.ref.message_id == "msg-1"
    assert message.ref.thread_id == "thread-1"
    assert message.from_addr is not None
    assert message.from_addr.address == "jobs@example.com"
    assert message.subject == "Application received"
    assert message.sent_at == NOW
    assert message.labels == ("INBOX",)
    assert message.body_text is None
    assert not hasattr(message, "snippet")
    assert page.next_sync_cursor is not None
    assert page.next_sync_cursor.value == "12345"

    assert [call[0] for call in transport.calls] == [
        "/gmail/v1/users/me/profile",
        "/gmail/v1/users/me/messages",
        "/gmail/v1/users/me/messages/msg-1",
    ]
    assert {call[2] for call in transport.calls} == {"access-token"}


def test_gmail_email_provider_fetches_selected_retained_bodies_with_secret_store() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    transport = FakeGmailTransport()
    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )
    connection = _connection()

    batch = asyncio.run(
        provider.fetch_message_bodies(
            connection,
            EmailBodyFetchRequest(
                refs=(
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-1",
                        thread_id="thread-1",
                    ),
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-html",
                        thread_id="thread-html",
                    ),
                ),
                max_body_bytes=10_000,
            ),
        )
    )

    assert batch.failures == ()
    assert [body.ref.message_id for body in batch.bodies] == ["msg-1", "msg-html"]
    assert batch.bodies[0].body_text == "Thanks for applying to Example Corp.\nNext steps soon."
    assert batch.bodies[0].body_source is EmailBodySource.TEXT_PLAIN
    assert batch.bodies[0].truncated is False
    assert batch.bodies[1].body_text == "Application update\nPlease schedule an interview."
    assert batch.bodies[1].body_source is EmailBodySource.HTML_CONVERTED

    body_calls = [
        (path, dict(query), token)
        for path, query, token in transport.calls
        if dict(query).get("format") == "full"
    ]
    assert [call[0] for call in body_calls] == [
        "/gmail/v1/users/me/messages/msg-1",
        "/gmail/v1/users/me/messages/msg-html",
    ]
    assert {call[2] for call in body_calls} == {"access-token"}
    assert all("snippet" not in call[1]["fields"] for call in body_calls)


def test_gmail_email_provider_returns_empty_failure_when_body_has_no_text() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=FakeGmailTransport(),
    )
    connection = _connection()

    batch = asyncio.run(
        provider.fetch_message_bodies(
            connection,
            EmailBodyFetchRequest(
                refs=(
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-empty",
                        thread_id="thread-empty",
                    ),
                ),
            ),
        )
    )

    assert batch.bodies == ()
    assert len(batch.failures) == 1
    assert batch.failures[0].ref.message_id == "msg-empty"
    assert batch.failures[0].reason is EmailBodyFetchFailureReason.EMPTY


def test_gmail_email_provider_returns_not_found_failure_for_deleted_body_message() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=DeletedMessageGmailTransport(),
    )
    connection = _connection()

    batch = asyncio.run(
        provider.fetch_message_bodies(
            connection,
            EmailBodyFetchRequest(
                refs=(
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-deleted",
                        thread_id="thread-deleted",
                    ),
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-1",
                        thread_id="thread-1",
                    ),
                ),
            ),
        )
    )

    assert [body.ref.message_id for body in batch.bodies] == ["msg-1"]
    assert len(batch.failures) == 1
    assert batch.failures[0].ref.message_id == "msg-deleted"
    assert batch.failures[0].reason is EmailBodyFetchFailureReason.NOT_FOUND


def test_gmail_email_provider_sanitizes_body_dto_validation_errors() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=FakeGmailTransport(),
    )
    connection = _connection()

    with pytest.raises(EmailProviderError) as error_info:
        asyncio.run(
            provider.fetch_message_bodies(
                connection,
                EmailBodyFetchRequest(
                    refs=(
                        EmailMessageRef(
                            account=connection.account,
                            message_id="msg-mislabelled-html",
                            thread_id="thread-mislabelled-html",
                        ),
                    ),
                ),
            )
        )

    assert error_info.value.public_message == "Gmail body fetching returned invalid data"
    assert "Sensitive application update" not in str(error_info.value)
    assert error_info.value.__cause__ is None


def test_gmail_email_provider_uses_html_when_plain_alternative_is_empty() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=FakeGmailTransport(),
    )
    connection = _connection()

    batch = asyncio.run(
        provider.fetch_message_bodies(
            connection,
            EmailBodyFetchRequest(
                refs=(
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-empty-plain-with-html",
                        thread_id="thread-empty-plain-with-html",
                    ),
                ),
            ),
        )
    )

    assert batch.failures == ()
    assert len(batch.bodies) == 1
    assert batch.bodies[0].body_text == "Application update\nBook an interview."
    assert batch.bodies[0].body_source is EmailBodySource.HTML_CONVERTED


def test_gmail_email_provider_truncates_without_splitting_utf8_characters() -> None:
    from app.providers.email.gmail import GmailEmailProvider

    provider = GmailEmailProvider(
        settings=_settings(),
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=FakeGmailTransport(),
    )
    connection = _connection()

    batch = asyncio.run(
        provider.fetch_message_bodies(
            connection,
            EmailBodyFetchRequest(
                refs=(
                    EmailMessageRef(
                        account=connection.account,
                        message_id="msg-unicode",
                        thread_id="thread-unicode",
                    ),
                ),
                max_body_bytes=3,
            ),
        )
    )

    assert batch.failures == ()
    assert len(batch.bodies) == 1
    assert batch.bodies[0].body_text == "é"
    assert batch.bodies[0].truncated is True
