from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from app.config import EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailConnection,
    EmailMetadataListRequest,
    EmailProviderAuthError,
    EmailProviderError,
    EmailSyncMode,
)
from app.providers.email.gmail import GMAIL_METADATA_HEADERS, GmailMessageLister
from app.security import SecretKind, SecretRef
from pydantic import SecretStr

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class FakeSecretStore:
    def __init__(self, secret: SecretStr | None) -> None:
        self.secret = secret

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return self.secret

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        self.secret = value

    async def delete_secret(self, ref: SecretRef) -> None:
        self.secret = None


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
        if path == "/gmail/v1/users/me/messages":
            return {
                "messages": [
                    {"id": "msg-1", "threadId": "thread-1"},
                    {"id": "msg-2", "threadId": "thread-2"},
                ],
                "nextPageToken": "next-page",
            }

        if path == "/gmail/v1/users/me/messages/msg-1":
            return {
                "id": "msg-1",
                "threadId": "thread-1",
                "labelIds": ["INBOX", "CATEGORY_PRIMARY"],
                "snippet": "Thanks for applying.",
                "sizeEstimate": 2048,
                "historyId": "12345",
            }

        if path == "/gmail/v1/users/me/messages/msg-2":
            return {
                "id": "msg-2",
                "threadId": "thread-2",
                "labelIds": ["SENT"],
                "payload": {"body": {"data": "base64-body-must-not-be-used"}},
                "sizeEstimate": 512,
            }

        raise AssertionError(f"unexpected Gmail path: {path}")


def test_gmail_message_lister_pages_metadata_without_body_content() -> None:
    transport = FakeGmailTransport()
    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )

    page = asyncio.run(
        lister.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(
                mode=EmailSyncMode.FULL_BACKFILL,
                page_size=2,
                page_token="page-1",
            ),
        )
    )

    assert page.next_page_token == "next-page"
    assert page.next_sync_cursor is None
    assert [message.ref.message_id for message in page.messages] == ["msg-1", "msg-2"]
    assert page.messages[0].ref.thread_id == "thread-1"
    assert page.messages[0].labels == ("INBOX", "CATEGORY_PRIMARY")
    assert page.messages[0].size_bytes == 2048
    assert page.messages[0].body_text is None
    assert not hasattr(page.messages[0], "snippet")

    list_path, list_query, list_token = transport.calls[0]
    assert list_path == "/gmail/v1/users/me/messages"
    assert dict(list_query) == {
        "fields": "messages(id,threadId),nextPageToken",
        "maxResults": "2",
        "pageToken": "page-1",
    }
    assert list_token == "access-token"

    for path, query, token in transport.calls[1:]:
        assert path.startswith("/gmail/v1/users/me/messages/msg-")
        assert ("format", "metadata") in query
        assert token == "access-token"
        metadata_fields = dict(query)["fields"]
        assert "snippet" not in metadata_fields
        assert "body" not in metadata_fields
        for header in GMAIL_METADATA_HEADERS:
            assert ("metadataHeaders", header) in query


def test_gmail_message_lister_handles_empty_pages_without_metadata_fetches() -> None:
    class EmptyTransport(FakeGmailTransport):
        async def get_json(
            self,
            path: str,
            *,
            query: tuple[tuple[str, str], ...],
            access_token: SecretStr,
        ) -> dict[str, object]:
            self.calls.append((path, query, access_token.get_secret_value()))
            return {"messages": []}

    transport = EmptyTransport()
    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )

    page = asyncio.run(
        lister.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=500),
        )
    )

    assert page.messages == ()
    assert page.next_page_token is None
    assert [call[0] for call in transport.calls] == ["/gmail/v1/users/me/messages"]


def test_gmail_message_lister_requires_stored_oauth_secret() -> None:
    transport = FakeGmailTransport()
    lister = GmailMessageLister(secret_store=FakeSecretStore(None), transport=transport)

    with pytest.raises(EmailProviderAuthError, match="Gmail authorization is required"):
        asyncio.run(
            lister.list_message_metadata(
                _connection(),
                EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=500),
            )
        )

    assert transport.calls == []


def test_gmail_message_lister_wraps_invalid_provider_metadata_without_raw_payload() -> None:
    class InvalidMetadataTransport(FakeGmailTransport):
        async def get_json(
            self,
            path: str,
            *,
            query: tuple[tuple[str, str], ...],
            access_token: SecretStr,
        ) -> dict[str, object]:
            self.calls.append((path, query, access_token.get_secret_value()))
            if path == "/gmail/v1/users/me/messages":
                return {"messages": [{"id": "msg-1", "threadId": "thread-1"}]}
            return {"id": "", "snippet": "Private recruiter feedback"}

    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=InvalidMetadataTransport(),
    )

    with pytest.raises(EmailProviderError) as exc_info:
        asyncio.run(
            lister.list_message_metadata(
                _connection(),
                EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=500),
            )
        )

    assert str(exc_info.value) == "Gmail metadata listing returned invalid data"
    assert "Private recruiter feedback" not in repr(exc_info.value)


def test_gmail_message_lister_rejects_page_sizes_above_gmail_limit() -> None:
    transport = FakeGmailTransport()
    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )

    with pytest.raises(EmailProviderError, match="Gmail metadata page size cannot exceed 500"):
        asyncio.run(
            lister.list_message_metadata(
                _connection(),
                EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=501),
            )
        )

    assert transport.calls == []


def _connection() -> EmailConnection:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailConnection(
        account=account,
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        connected_at=NOW,
    )
