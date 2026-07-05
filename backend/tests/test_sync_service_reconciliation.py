from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.config import EmailProviderName
from app.db.repositories import EmailRepository
from app.providers.email import (
    EmailAccountRef,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataPage,
)
from app.services.sync_service import build_backfill_reconciliation_metrics

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_backfill_reconciliation_metrics_compare_local_count_to_provider_pages() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    pages = (
        metadata_page(account, ("gmail-msg-1", "gmail-msg-2"), next_page_token="page-2"),
        metadata_page(account, ("gmail-msg-3",)),
    )

    metrics = build_backfill_reconciliation_metrics(
        provider=EmailProviderName.GMAIL,
        email_repository=repository_with_raw_email_ids(("gmail-msg-1", "gmail-msg-2")),
        pages=pages,
    )

    assert metrics.provider is EmailProviderName.GMAIL
    assert metrics.provider_page_count == 2
    assert metrics.provider_message_count == 3
    assert metrics.provider_unique_message_count == 3
    assert metrics.provider_duplicate_message_count == 0
    assert metrics.local_raw_email_count == 2
    assert metrics.local_minus_provider_unique_count == -1
    assert metrics.missing_local_message_count == 1
    assert metrics.extra_local_message_count == 0
    assert metrics.reconciled is False


def test_backfill_reconciliation_metrics_reconcile_against_unique_provider_messages() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    pages = (
        metadata_page(account, ("gmail-msg-1", "gmail-msg-2"), next_page_token="page-2"),
        metadata_page(account, ("gmail-msg-2",)),
    )

    metrics = build_backfill_reconciliation_metrics(
        provider=EmailProviderName.GMAIL,
        email_repository=repository_with_raw_email_ids(("gmail-msg-1", "gmail-msg-2")),
        pages=pages,
    )

    assert metrics.provider_message_count == 3
    assert metrics.provider_unique_message_count == 2
    assert metrics.provider_duplicate_message_count == 1
    assert metrics.local_minus_provider_unique_count == 0
    assert metrics.missing_local_message_count == 0
    assert metrics.extra_local_message_count == 0
    assert metrics.reconciled is True


def test_backfill_reconciliation_metrics_detects_swapped_local_provider_ids() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    pages = (metadata_page(account, ("gmail-msg-1", "gmail-msg-2")),)

    metrics = build_backfill_reconciliation_metrics(
        provider=EmailProviderName.GMAIL,
        email_repository=repository_with_raw_email_ids(("gmail-msg-1", "stale-msg-1")),
        pages=pages,
    )

    assert metrics.local_raw_email_count == 2
    assert metrics.local_minus_provider_unique_count == 0
    assert metrics.missing_local_message_count == 1
    assert metrics.extra_local_message_count == 1
    assert metrics.reconciled is False


def test_email_repository_counts_raw_email_rows_for_provider() -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    connection.executemany(
        """
        INSERT INTO raw_emails (
            id,
            thread_id,
            from_addr,
            to_addr,
            subject,
            sent_at,
            body_text,
            body_retention_state,
            labels,
            provider,
            ingested_at
        ) VALUES (
            ?, NULL, NULL, NULL, NULL, NULL, NULL, 'metadata_only', '[]', ?, ?
        )
        """,
        (
            ("gmail-msg-1", "gmail", NOW.isoformat()),
            ("gmail-msg-2", "gmail", NOW.isoformat()),
            ("outlook-msg-1", "outlook", NOW.isoformat()),
        ),
    )

    repository = EmailRepository(connection)

    assert repository.count_raw_emails() == 3
    assert repository.count_raw_emails(provider=EmailProviderName.GMAIL) == 2
    assert repository.list_raw_email_ids(provider=EmailProviderName.GMAIL) == [
        "gmail-msg-1",
        "gmail-msg-2",
    ]


def metadata_page(
    account: EmailAccountRef,
    message_ids: tuple[str, ...],
    *,
    next_page_token: str | None = None,
) -> EmailMetadataPage:
    return EmailMetadataPage(
        messages=tuple(
            EmailMessageMetadata(
                ref=EmailMessageRef(account=account, message_id=message_id),
                received_at=NOW,
            )
            for message_id in message_ids
        ),
        next_page_token=next_page_token,
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


def repository_with_raw_email_ids(message_ids: tuple[str, ...]) -> EmailRepository:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    connection.executemany(
        """
        INSERT INTO raw_emails (
            id,
            thread_id,
            from_addr,
            to_addr,
            subject,
            sent_at,
            body_text,
            body_retention_state,
            labels,
            provider,
            ingested_at
        ) VALUES (
            ?, NULL, NULL, NULL, NULL, NULL, NULL, 'metadata_only', '[]', 'gmail', ?
        )
        """,
        [(message_id, NOW.isoformat()) for message_id in message_ids],
    )
    return EmailRepository(connection)
