from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
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

BACKEND_ROOT = Path(__file__).resolve().parents[1]
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
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
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


def test_classification_candidate_queries_skip_empty_retained_body_text(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)
    insert_raw_email(connection, "empty-retained", body_text="")
    insert_raw_email(connection, "nonempty-retained", body_text="Candidate body.")
    connection.commit()

    stats = repository.get_classification_candidate_stats(
        provider=EmailProviderName.GMAIL,
        model="llama3.1",
        prompt_version="v2",
    )
    candidates = repository.list_classification_candidates(
        provider=EmailProviderName.GMAIL,
        model="llama3.1",
        prompt_version="v2",
        limit=10,
    )

    assert stats.candidate_count == 1
    assert stats.body_text_char_count == len("Candidate body.")
    assert [candidate.email_id for candidate in candidates] == ["nonempty-retained"]


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


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


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    body_text: str | None,
) -> None:
    connection.execute(
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "me@example.test",
            "Application update",
            NOW.isoformat(),
            body_text,
            RawEmailBodyRetentionState.RETAINED.value,
            "[]",
            EmailProviderName.GMAIL.value,
            NOW.isoformat(),
        ),
    )
