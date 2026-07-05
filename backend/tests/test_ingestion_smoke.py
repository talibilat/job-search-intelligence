from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

from app.config import GMAIL_READONLY_SCOPE, EmailProviderName
from app.db.repositories import EmailRepository, SyncStateRepository
from app.models import RawEmailBodyRetentionState, RawEmailRecord
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
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef
from app.services.sync_service import EmailSyncService, SyncService

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class PaginatedMetadataProvider:
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
        if request.page_token is None:
            return metadata_page(
                connection.account,
                ("provider-msg-1", "provider-msg-2"),
                next_page_token="page-2",
            )
        if request.page_token == "page-2":
            return metadata_page(connection.account, ("provider-msg-3",))

        raise AssertionError(f"unexpected page token: {request.page_token}")


def test_ingestion_smoke_lists_every_provider_metadata_page() -> None:
    provider = PaginatedMetadataProvider()
    service = EmailSyncService(provider=provider, page_size=2)
    connection = email_connection()

    first_result = asyncio.run(service.list_metadata_page(connection=connection))
    second_result = asyncio.run(
        service.list_metadata_page(
            connection=connection,
            mode=first_result.mode,
            page_token=first_result.page.next_page_token,
        )
    )

    results = (first_result, second_result)

    assert [result.mode for result in results] == [
        EmailSyncMode.FULL_BACKFILL,
        EmailSyncMode.FULL_BACKFILL,
    ]
    assert [request.page_token for request in provider.requests] == [None, "page-2"]
    assert [request.page_size for request in provider.requests] == [2, 2]
    assert [message.ref.message_id for result in results for message in result.page.messages] == [
        "provider-msg-1",
        "provider-msg-2",
        "provider-msg-3",
    ]


def test_ingestion_smoke_raw_email_writes_are_idempotent() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    repository = EmailRepository(connection)
    email = raw_email_record("provider-msg-1")

    repository.upsert_raw_emails((email,))
    repository.upsert_raw_emails((email,))

    row = connection.execute("SELECT COUNT(*) FROM raw_emails").fetchone()
    assert row is not None
    assert row[0] == 1

    stored = repository.fetch_one(
        "SELECT * FROM raw_emails WHERE id = ?",
        ("provider-msg-1",),
    )
    assert stored == email


def test_ingestion_smoke_metadata_replay_preserves_retained_raw_email_body() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    repository = EmailRepository(connection)
    retained_email = raw_email_record(
        "provider-msg-1",
        body_text="Retained synthetic body.",
        body_retention_state=RawEmailBodyRetentionState.RETAINED,
    )
    metadata_only_replay = raw_email_record("provider-msg-1")

    repository.upsert_raw_emails((retained_email,))
    repository.upsert_raw_emails((metadata_only_replay,))

    stored = repository.fetch_one(
        "SELECT * FROM raw_emails WHERE id = ?",
        ("provider-msg-1",),
    )
    assert stored is not None
    assert stored.body_text == "Retained synthetic body."
    assert stored.body_retention_state is RawEmailBodyRetentionState.RETAINED


def test_ingestion_smoke_sync_state_status_tracks_latest_cursor() -> None:
    connection = sqlite3.connect(":memory:")
    create_email_sync_state_table(connection)
    service = SyncService(sync_state_repository=SyncStateRepository(connection))
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")

    assert service.get_sync_status(account) is None

    service.store_sync_cursor(
        EmailProviderCursor(account=account, value="history-10", issued_at=NOW),
        updated_at=NOW,
    )

    status = service.get_sync_status(account)

    assert status is not None
    assert status.account == account
    assert status.cursor is not None
    assert status.cursor.value == "history-10"
    assert status.cursor.issued_at == NOW
    assert status.last_state_update_at == NOW


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


def metadata_page(
    account: EmailAccountRef,
    message_ids: tuple[str, ...],
    *,
    next_page_token: str | None = None,
) -> EmailMetadataPage:
    return EmailMetadataPage(
        messages=tuple(
            EmailMessageMetadata(
                ref=EmailMessageRef(
                    account=account,
                    message_id=message_id,
                    thread_id=f"thread-{message_id}",
                ),
                from_addr=EmailAddress(address="jobs@example.test"),
                subject="Application received",
                received_at=NOW,
            )
            for message_id in message_ids
        ),
        next_page_token=next_page_token,
    )


def raw_email_record(
    message_id: str,
    *,
    body_text: str | None = None,
    body_retention_state: RawEmailBodyRetentionState = RawEmailBodyRetentionState.METADATA_ONLY,
) -> RawEmailRecord:
    return RawEmailRecord(
        id=message_id,
        thread_id=f"thread-{message_id}",
        from_addr="jobs@example.test",
        to_addr="me@example.com",
        subject="Application received",
        sent_at=NOW,
        body_text=body_text,
        body_retention_state=body_retention_state,
        labels=["INBOX"],
        provider=EmailProviderName.GMAIL.value,
        ingested_at=NOW,
    )


def create_raw_emails_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE raw_emails (
            id TEXT PRIMARY KEY,
            thread_id TEXT,
            from_addr TEXT,
            to_addr TEXT,
            subject TEXT,
            sent_at TEXT,
            body_text TEXT,
            body_retention_state TEXT NOT NULL,
            labels TEXT NOT NULL,
            provider TEXT NOT NULL,
            ingested_at TEXT NOT NULL
        )
        """,
    )


def create_email_sync_state_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE email_sync_state (
            provider TEXT NOT NULL,
            account_id TEXT NOT NULL,
            sync_cursor TEXT NOT NULL,
            cursor_issued_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (provider, account_id)
        )
        """,
    )
