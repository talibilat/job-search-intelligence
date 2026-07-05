from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
from app.config import EmailProviderName
from app.db.repositories import EmailRepository
from app.models import RawEmailBodyRetentionState
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailBodySource,
    EmailMessageBody,
    EmailMessageMetadata,
    EmailMessageRef,
)

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("retention_state", "body_text"),
    [
        (RawEmailBodyRetentionState.RETAINED, "Retained candidate body."),
        (RawEmailBodyRetentionState.DEBUGGING, "Debugging reconciliation body."),
    ],
)
def test_upsert_retained_bodies_inserts_missing_raw_email_and_survives_metadata_replay(
    retention_state: RawEmailBodyRetentionState,
    body_text: str,
) -> None:
    connection = sqlite3.connect(":memory:")
    create_raw_emails_table(connection)
    repository = EmailRepository(connection)
    message_body = email_message_body("gmail-msg-1", body_text=body_text)

    written_count = repository.upsert_retained_bodies(
        (message_body,),
        retention_state=retention_state,
    )
    replay_written_count = repository.upsert_retained_bodies(
        (message_body,),
        retention_state=retention_state,
    )
    repository.upsert_metadata_only(
        (metadata_message("gmail-msg-1"),),
        ingested_at=NOW,
    )

    stored = repository.fetch_one(
        "SELECT * FROM raw_emails WHERE id = ?",
        ("gmail-msg-1",),
    )
    count_row = connection.execute("SELECT COUNT(*) FROM raw_emails").fetchone()
    assert written_count == 1
    assert replay_written_count == 1
    assert count_row is not None
    assert count_row[0] == 1
    assert stored is not None
    assert stored.thread_id == "thread-gmail-msg-1"
    assert stored.subject == "Application received"
    assert stored.body_text == body_text
    assert stored.body_retention_state is retention_state


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
            ingested_at TEXT NOT NULL,
            CHECK (
                (body_retention_state = 'metadata_only' AND body_text IS NULL)
                OR (body_retention_state IN ('retained', 'debugging') AND body_text IS NOT NULL)
            )
        )
        """,
    )


def email_message_body(message_id: str, *, body_text: str) -> EmailMessageBody:
    return EmailMessageBody(
        ref=email_message_ref(message_id),
        body_text=body_text,
        body_source=EmailBodySource.TEXT_PLAIN,
        truncated=False,
        fetched_at=NOW,
    )


def metadata_message(message_id: str) -> EmailMessageMetadata:
    return EmailMessageMetadata(
        ref=email_message_ref(message_id),
        from_addr=EmailAddress(address="jobs@example.test"),
        to_addrs=(EmailAddress(address="me@example.com"),),
        subject="Application received",
        sent_at=NOW,
        labels=("INBOX",),
    )


def email_message_ref(message_id: str) -> EmailMessageRef:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailMessageRef(
        account=account,
        message_id=message_id,
        thread_id=f"thread-{message_id}",
    )
