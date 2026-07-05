from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.message import Message
from urllib.error import HTTPError

import pytest
from app.config import EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailConnection,
    EmailMetadataListRequest,
    EmailProviderAuthError,
    EmailProviderCursor,
    EmailProviderError,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.providers.email.gmail import (
    GMAIL_METADATA_HEADERS,
    GmailMessageLister,
    UrllibGmailApiTransport,
)
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
        if path == "/gmail/v1/users/me/profile":
            return {"historyId": "12345"}

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
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Jane Recruiter <jane@example.com>"},
                        {
                            "name": "To",
                            "value": "Candidate <me@example.com>, jobs@example.com",
                        },
                        {"name": "Cc", "value": "Hiring Team <hiring@example.com>"},
                        {"name": "Subject", "value": "Application received"},
                        {"name": "Date", "value": "Sun, 05 Jul 2026 12:00:00 +0000"},
                        {"name": "Message-ID", "value": "<gmail-msg-1@example.com>"},
                    ]
                },
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
            ),
        )
    )

    assert page.next_page_token is not None
    assert page.next_page_token != "next-page"
    assert page.next_sync_cursor is None
    assert [message.ref.message_id for message in page.messages] == ["msg-1", "msg-2"]
    assert page.messages[0].ref.thread_id == "thread-1"
    assert page.messages[0].from_addr is not None
    assert page.messages[0].from_addr.address == "jane@example.com"
    assert page.messages[0].from_addr.display_name == "Jane Recruiter"
    assert [address.address for address in page.messages[0].to_addrs] == [
        "me@example.com",
        "jobs@example.com",
    ]
    assert [address.display_name for address in page.messages[0].to_addrs] == ["Candidate", None]
    assert [address.address for address in page.messages[0].cc_addrs] == ["hiring@example.com"]
    assert page.messages[0].subject == "Application received"
    assert page.messages[0].sent_at == datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    assert page.messages[0].rfc822_message_id == "<gmail-msg-1@example.com>"
    assert page.messages[0].labels == ("INBOX", "CATEGORY_PRIMARY")
    assert page.messages[0].size_bytes == 2048
    assert page.messages[0].body_text is None
    assert not hasattr(page.messages[0], "snippet")

    profile_path, profile_query, profile_token = transport.calls[0]
    assert profile_path == "/gmail/v1/users/me/profile"
    assert dict(profile_query) == {"fields": "historyId"}
    assert profile_token == "access-token"

    list_path, list_query, list_token = transport.calls[1]
    assert list_path == "/gmail/v1/users/me/messages"
    assert dict(list_query) == {
        "fields": "messages(id,threadId),nextPageToken",
        "maxResults": "2",
    }
    assert list_token == "access-token"

    for path, query, token in transport.calls[2:]:
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
            if path == "/gmail/v1/users/me/profile":
                return {"historyId": "history-empty"}
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
    assert page.next_sync_cursor is not None
    assert page.next_sync_cursor.value == "history-empty"
    assert [call[0] for call in transport.calls] == [
        "/gmail/v1/users/me/profile",
        "/gmail/v1/users/me/messages",
    ]


def test_gmail_message_lister_returns_captured_profile_history_id_on_final_page() -> None:
    class FinalPageTransport(FakeGmailTransport):
        async def get_json(
            self,
            path: str,
            *,
            query: tuple[tuple[str, str], ...],
            access_token: SecretStr,
        ) -> dict[str, object]:
            self.calls.append((path, query, access_token.get_secret_value()))
            if path == "/gmail/v1/users/me/messages":
                return {"messages": []}
            if path == "/gmail/v1/users/me/profile":
                return {"historyId": "history-complete"}
            raise AssertionError(f"unexpected Gmail path: {path}")

    transport = FinalPageTransport()
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

    assert page.next_page_token is None
    assert page.next_sync_cursor is not None
    assert page.next_sync_cursor.value == "history-complete"
    assert [call[0] for call in transport.calls] == [
        "/gmail/v1/users/me/profile",
        "/gmail/v1/users/me/messages",
    ]


def test_gmail_message_lister_withholds_full_backfill_cursor_until_final_page() -> None:
    class PaginatedTransport(FakeGmailTransport):
        async def get_json(
            self,
            path: str,
            *,
            query: tuple[tuple[str, str], ...],
            access_token: SecretStr,
        ) -> dict[str, object]:
            self.calls.append((path, query, access_token.get_secret_value()))
            if path == "/gmail/v1/users/me/profile":
                return {"historyId": "anchor-before-backfill"}
            if path == "/gmail/v1/users/me/messages":
                query_dict = dict(query)
                if "pageToken" not in query_dict:
                    return {
                        "messages": [{"id": "msg-1", "threadId": "thread-1"}],
                        "nextPageToken": "gmail-page-2",
                    }
                if query_dict["pageToken"] == "gmail-page-2":
                    return {"messages": [{"id": "msg-2", "threadId": "thread-2"}]}
            if path == "/gmail/v1/users/me/messages/msg-1":
                return {"id": "msg-1", "threadId": "thread-1", "payload": {"headers": []}}
            if path == "/gmail/v1/users/me/messages/msg-2":
                return {"id": "msg-2", "threadId": "thread-2", "payload": {"headers": []}}
            raise AssertionError(f"unexpected Gmail path: {path}")

    transport = PaginatedTransport()
    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )

    first_page = asyncio.run(
        lister.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(mode=EmailSyncMode.FULL_BACKFILL, page_size=1),
        )
    )
    assert first_page.next_page_token is not None

    second_page = asyncio.run(
        lister.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(
                mode=EmailSyncMode.FULL_BACKFILL,
                page_size=1,
                page_token=first_page.next_page_token,
            ),
        )
    )

    assert [message.ref.message_id for message in first_page.messages] == ["msg-1"]
    assert first_page.next_sync_cursor is None
    assert [message.ref.message_id for message in second_page.messages] == ["msg-2"]
    assert second_page.next_page_token is None
    assert second_page.next_sync_cursor is not None
    assert second_page.next_sync_cursor.value == "anchor-before-backfill"
    assert [call[0] for call in transport.calls].count("/gmail/v1/users/me/profile") == 1
    assert dict(transport.calls[3][1])["pageToken"] == "gmail-page-2"


def test_gmail_message_lister_uses_history_for_incremental_metadata_sync() -> None:
    class HistoryTransport(FakeGmailTransport):
        async def get_json(
            self,
            path: str,
            *,
            query: tuple[tuple[str, str], ...],
            access_token: SecretStr,
        ) -> dict[str, object]:
            self.calls.append((path, query, access_token.get_secret_value()))
            if path == "/gmail/v1/users/me/history":
                return {
                    "history": [
                        {
                            "id": "1002",
                            "messagesAdded": [
                                {"message": {"id": "msg-3", "threadId": "thread-3"}},
                                {"message": {"id": "msg-3", "threadId": "thread-3"}},
                            ],
                        }
                    ],
                    "nextPageToken": "history-page-2",
                    "historyId": "1003",
                }
            if path == "/gmail/v1/users/me/messages/msg-3":
                return {
                    "id": "msg-3",
                    "threadId": "thread-3",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Jobs <jobs@example.com>"},
                            {"name": "Subject", "value": "Application update"},
                            {"name": "Date", "value": "Sun, 05 Jul 2026 12:01:00 +0000"},
                        ]
                    },
                    "sizeEstimate": 1024,
                }
            raise AssertionError(f"unexpected Gmail path: {path}")

    transport = HistoryTransport()
    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )
    cursor = EmailProviderCursor(
        account=_connection().account,
        value="1001",
        issued_at=NOW,
    )

    page = asyncio.run(
        lister.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(
                mode=EmailSyncMode.INCREMENTAL,
                page_size=2,
                page_token="history-page-1",
                sync_cursor=cursor,
            ),
        )
    )

    assert [message.ref.message_id for message in page.messages] == ["msg-3"]
    assert page.next_page_token == "history-page-2"
    assert page.next_sync_cursor is None
    history_path, history_query, history_token = transport.calls[0]
    assert history_path == "/gmail/v1/users/me/history"
    assert dict(history_query) == {
        "fields": "history(id,messagesAdded(message(id,threadId))),nextPageToken,historyId",
        "historyTypes": "messageAdded",
        "maxResults": "2",
        "pageToken": "history-page-1",
        "startHistoryId": "1001",
    }
    assert history_token == "access-token"
    assert [call[0] for call in transport.calls[1:]] == ["/gmail/v1/users/me/messages/msg-3"]


def test_gmail_message_lister_returns_history_cursor_after_final_incremental_page() -> None:
    class FinalHistoryTransport(FakeGmailTransport):
        async def get_json(
            self,
            path: str,
            *,
            query: tuple[tuple[str, str], ...],
            access_token: SecretStr,
        ) -> dict[str, object]:
            self.calls.append((path, query, access_token.get_secret_value()))
            if path == "/gmail/v1/users/me/history":
                return {"history": [], "historyId": "1004"}
            raise AssertionError(f"unexpected Gmail path: {path}")

    transport = FinalHistoryTransport()
    lister = GmailMessageLister(
        secret_store=FakeSecretStore(SecretStr("access-token")),
        transport=transport,
    )
    cursor = EmailProviderCursor(
        account=_connection().account,
        value="1003",
        issued_at=NOW,
    )

    page = asyncio.run(
        lister.list_message_metadata(
            _connection(),
            EmailMetadataListRequest(
                mode=EmailSyncMode.INCREMENTAL,
                page_size=2,
                sync_cursor=cursor,
            ),
        )
    )

    assert page.messages == ()
    assert page.next_page_token is None
    assert page.next_sync_cursor is not None
    assert page.next_sync_cursor.value == "1004"


def test_gmail_history_404_maps_to_expired_sync_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_history_not_found(*args: object, **kwargs: object) -> object:
        raise HTTPError(
            url="https://gmail.example.test/gmail/v1/users/me/history",
            code=404,
            msg="Not Found",
            hdrs=Message(),
            fp=None,
        )

    monkeypatch.setattr("app.providers.email.gmail.urlopen", raise_history_not_found)
    transport = UrllibGmailApiTransport(base_url="https://gmail.example.test")

    with pytest.raises(EmailSyncCursorExpiredError, match="Gmail incremental sync cursor expired"):
        asyncio.run(
            transport.get_json(
                "/gmail/v1/users/me/history",
                query=(("startHistoryId", "1001"),),
                access_token=SecretStr("access-token"),
            )
        )


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
            if path == "/gmail/v1/users/me/profile":
                return {"historyId": "12345"}
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
