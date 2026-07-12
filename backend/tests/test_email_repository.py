from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import EmailProviderName
from app.db.repositories import EmailRepository
from app.models import RawEmailBodyRetentionState, RawEmailPreviewPage
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


def test_public_id_migration_backfills_unique_opaque_identifiers(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "20260710_0201")
    connection = sqlite3.connect(database_path)
    for index in range(3):
        insert_raw_email(connection, f"legacy-{index}", body_text="Legacy body")
    connection.commit()
    connection.close()

    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    public_ids = [row[0] for row in connection.execute("SELECT public_id FROM raw_emails")]
    indexes = connection.execute("PRAGMA index_list('raw_emails')").fetchall()
    table_info = connection.execute("PRAGMA table_info('raw_emails')").fetchall()
    public_id_column = next(row for row in table_info if row[1] == "public_id")
    assert len(set(public_ids)) == 3
    assert all(re.fullmatch(r"[0-9a-f]{32}", public_id) for public_id in public_ids)
    assert any(row[1] == "ux_raw_emails_public_id" and row[2] == 1 for row in indexes)
    assert public_id_column[3] == 1  # NOT NULL so DTO reads can rely on a present value
    retention_guard = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'raw_emails' AND type = 'table'"
    ).fetchone()[0]
    assert "ck_raw_emails_body_text_matches_retention_state" in retention_guard


def test_repository_upserts_populate_and_preserve_public_id(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)

    repository.upsert_metadata_only((metadata_message("gmail-msg-1"),), ingested_at=NOW)
    original_public_id = connection.execute(
        "SELECT public_id FROM raw_emails WHERE id = 'gmail-msg-1'"
    ).fetchone()[0]
    repository.upsert_metadata_only((metadata_message("gmail-msg-1"),), ingested_at=NOW)
    replayed_public_id = connection.execute(
        "SELECT public_id FROM raw_emails WHERE id = 'gmail-msg-1'"
    ).fetchone()[0]

    assert re.fullmatch(r"[0-9a-f]{32}", original_public_id)
    assert replayed_public_id == original_public_id


def test_paginate_email_previews_returns_page_totals_window_and_joined_fields(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)
    messages = tuple(metadata_message(f"message-{index:02d}") for index in range(23))
    repository.upsert_metadata_only(messages, ingested_at=NOW)
    for index in range(23):
        sent_at = NOW - timedelta(days=index)
        connection.execute(
            "UPDATE raw_emails SET sent_at = ? WHERE id = ?",
            (sent_at.isoformat(), f"message-{index:02d}"),
        )
    connection.execute(
        "INSERT INTO email_filter_decisions "
        "(email_id, strategy, outcome, reason, decided_at) "
        "VALUES ('message-10', 'broad_job_search', 'candidate', 'subject:job', ?)",
        (NOW.isoformat(),),
    )
    connection.execute(
        "INSERT INTO email_classifications "
        "(email_id, is_job_related, category, confidence, model, prompt_version, classified_at) "
        "VALUES ('message-10', 1, 'interview_invite', 0.9, 'test', 'v1', ?)",
        (NOW.isoformat(),),
    )
    connection.commit()

    page = repository.paginate_email_previews(
        provider=EmailProviderName.GMAIL,
        page=2,
        page_size=5,
        sent_after=NOW - timedelta(days=20),
        sent_before=NOW - timedelta(days=2),
    )

    assert isinstance(page, RawEmailPreviewPage)
    assert (page.page, page.page_size, page.total_items, page.total_pages) == (2, 5, 18, 4)
    assert [item.subject for item in page.items] == ["Application received"] * 5
    assert [item.sent_at for item in page.items] == [NOW - timedelta(days=i) for i in range(8, 13)]
    assert page.items[2].filter_outcome == "candidate"
    assert page.items[2].classification_category == "interview_invite"
    assert all(re.fullmatch(r"[0-9a-f]{32}", item.public_id) for item in page.items)


def test_paginate_email_previews_normalizes_window_bounds_to_utc(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)
    repository.upsert_metadata_only((metadata_message("utc-msg"),), ingested_at=NOW)
    connection.execute(
        "UPDATE raw_emails SET sent_at = ? WHERE id = 'utc-msg'",
        (NOW.isoformat(),),
    )
    connection.commit()
    offset_boundary = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))

    included = repository.paginate_email_previews(
        provider=EmailProviderName.GMAIL,
        page=1,
        page_size=10,
        sent_after=offset_boundary,
        sent_before=None,
    )
    excluded = repository.paginate_email_previews(
        provider=EmailProviderName.GMAIL,
        page=1,
        page_size=10,
        sent_after=None,
        sent_before=offset_boundary,
    )

    assert included.total_items == 1
    assert excluded.total_items == 0
    with pytest.raises(ValueError, match="timezone-aware"):
        repository.paginate_email_previews(
            provider=EmailProviderName.GMAIL,
            page=1,
            page_size=10,
            sent_after=NOW.replace(tzinfo=None),
            sent_before=None,
        )


def test_paginate_email_previews_tolerates_missing_classifications_table(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)
    repository.upsert_metadata_only((metadata_message("no-classify"),), ingested_at=NOW)
    connection.execute("DROP TABLE email_classifications")
    connection.commit()

    page = repository.paginate_email_previews(
        provider=EmailProviderName.GMAIL,
        page=1,
        page_size=10,
        sent_after=None,
        sent_before=None,
    )

    assert page.total_items == 1
    assert page.items[0].classification_category is None
    assert page.items[0].classification_is_job_related is None


def test_paginate_email_previews_uses_id_as_stable_tie_breaker(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)
    repository.upsert_metadata_only(
        (metadata_message("tie-a"), metadata_message("tie-c"), metadata_message("tie-b")),
        ingested_at=NOW,
    )

    page = repository.paginate_email_previews(
        provider=EmailProviderName.GMAIL,
        page=1,
        page_size=10,
        sent_after=None,
        sent_before=None,
    )

    public_ids_by_message_id = dict(
        connection.execute("SELECT id, public_id FROM raw_emails").fetchall()
    )
    assert [item.public_id for item in page.items] == [
        public_ids_by_message_id[message_id] for message_id in ("tie-c", "tie-b", "tie-a")
    ]


def test_get_reader_record_resolves_by_public_id_and_provider(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = EmailRepository(connection)
    repository.upsert_retained_bodies((email_message_body("reader-1", body_text="Private body"),))
    public_id = connection.execute(
        "SELECT public_id FROM raw_emails WHERE id = 'reader-1'"
    ).fetchone()[0]

    record = repository.get_reader_record(public_id, EmailProviderName.GMAIL)

    assert record is not None
    assert record.public_id == public_id
    assert record.provider_message_id == "reader-1"
    assert record.thread_id == "thread-reader-1"
    assert record.body_text == "Private body"
    assert record.provider == EmailProviderName.GMAIL.value
    assert repository.get_reader_record("0" * 32, EmailProviderName.GMAIL) is None
    connection.execute("UPDATE raw_emails SET provider = 'outlook' WHERE id = 'reader-1'")
    connection.commit()
    assert repository.get_reader_record(public_id, EmailProviderName.GMAIL) is None


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
    config = migration_config(database_path)
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def migration_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    return config


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
