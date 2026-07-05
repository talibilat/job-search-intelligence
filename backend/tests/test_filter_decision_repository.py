from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import EmailProviderName
from app.db.repositories import EmailFilterDecisionRepository, EmailRepository
from app.models import (
    EmailFilterDecisionOutcome,
    EmailFilterDecisionRecord,
)
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailCandidateQueryStrategy,
    EmailMessageMetadata,
    EmailMessageRef,
)
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_filter_decision_repository_upserts_outcome_and_reason(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    EmailRepository(connection).upsert_metadata_only(
        (metadata_message("gmail-msg-1"),),
        ingested_at=NOW,
    )
    repository = EmailFilterDecisionRepository(connection)

    first_count = repository.upsert_filter_decisions(
        (
            EmailFilterDecisionRecord(
                email_id="gmail-msg-1",
                strategy=EmailCandidateQueryStrategy.BROAD_JOB_SEARCH,
                outcome=EmailFilterDecisionOutcome.CANDIDATE,
                reason="sender_domain:greenhouse.io",
                decided_at=NOW,
            ),
        )
    )
    second_count = repository.upsert_filter_decisions(
        (
            EmailFilterDecisionRecord(
                email_id="gmail-msg-1",
                strategy=EmailCandidateQueryStrategy.BROAD_JOB_SEARCH,
                outcome=EmailFilterDecisionOutcome.REJECTED,
                reason="excluded_label:spam",
                decided_at=NOW + timedelta(minutes=5),
            ),
        )
    )

    stored = repository.fetch_one(
        "SELECT * FROM email_filter_decisions WHERE email_id = ? AND strategy = ?",
        ("gmail-msg-1", "broad_job_search"),
    )
    count_row = connection.execute("SELECT COUNT(*) FROM email_filter_decisions").fetchone()
    assert first_count == 1
    assert second_count == 1
    assert count_row is not None
    assert count_row[0] == 1
    assert stored is not None
    assert stored.email_id == "gmail-msg-1"
    assert stored.outcome is EmailFilterDecisionOutcome.REJECTED
    assert stored.reason == "excluded_label:spam"
    assert stored.decided_at == NOW + timedelta(minutes=5)


def test_filter_decision_record_rejects_unknown_strategy() -> None:
    with pytest.raises(ValidationError):
        EmailFilterDecisionRecord.model_validate(
            {
                "email_id": "gmail-msg-1",
                "strategy": "misspelled_strategy",
                "outcome": EmailFilterDecisionOutcome.CANDIDATE,
                "reason": "sender_domain:greenhouse.io",
                "decided_at": NOW,
            }
        )


def test_filter_decision_table_rejects_unknown_strategy(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    EmailRepository(connection).upsert_metadata_only(
        (metadata_message("gmail-msg-1"),),
        ingested_at=NOW,
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO email_filter_decisions (
                email_id,
                strategy,
                outcome,
                reason,
                decided_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "gmail-msg-1",
                "misspelled_strategy",
                EmailFilterDecisionOutcome.CANDIDATE.value,
                "sender_domain:greenhouse.io",
                NOW.isoformat(),
            ),
        )


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def metadata_message(message_id: str) -> EmailMessageMetadata:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailMessageMetadata(
        ref=EmailMessageRef(
            account=account,
            message_id=message_id,
            thread_id=f"thread-{message_id}",
        ),
        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
        to_addrs=(EmailAddress(address="me@example.com"),),
        subject="Application received",
        sent_at=NOW,
        labels=("INBOX",),
    )
