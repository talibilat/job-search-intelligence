from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import EmailProviderName
from app.db.repositories import EmailRepository
from app.models import RawEmailBodyRetentionState
from app.services.email_chunking import EmailChunkingService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def test_build_chunks_uses_only_retained_job_related_email_bodies(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "job-retained", body_text="Recruiter said hello.")
    insert_raw_email(connection, "not-job", body_text="Newsletter body.")
    insert_raw_email(
        connection,
        "debugging-body",
        body_text="Debugging retained body.",
        retention_state=RawEmailBodyRetentionState.DEBUGGING,
    )
    insert_raw_email(
        connection,
        "metadata-only",
        body_text=None,
        retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
    )
    insert_classification(connection, "job-retained", is_job_related=True)
    insert_classification(connection, "not-job", is_job_related=False)
    insert_classification(connection, "debugging-body", is_job_related=True)
    insert_classification(connection, "metadata-only", is_job_related=True)
    connection.commit()
    service = EmailChunkingService(EmailRepository(connection), max_chars=80, overlap_chars=10)

    chunks = service.build_chunks(limit=10)

    assert [(chunk.email_id, chunk.chunk_index, chunk.content) for chunk in chunks] == [
        ("job-retained", 0, "Recruiter said hello."),
    ]


def test_build_chunks_splits_long_email_bodies_with_overlap(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    body = "A" * 35 + "\n\n" + "B" * 35 + "\n\n" + "C" * 35
    insert_raw_email(connection, "long-job", body_text=body)
    insert_classification(connection, "long-job", is_job_related=True)
    connection.commit()
    service = EmailChunkingService(EmailRepository(connection), max_chars=80, overlap_chars=8)

    chunks = service.build_chunks(limit=10)

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert all(chunk.email_id == "long-job" for chunk in chunks)
    assert all(len(chunk.content) <= 80 for chunk in chunks)
    assert chunks[0].content.endswith("B" * 35)
    assert chunks[1].content.startswith("B" * 8)
    assert chunks[1].content.endswith("C" * 35)


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    body_text: str | None,
    retention_state: RawEmailBodyRetentionState = RawEmailBodyRetentionState.RETAINED,
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
            retention_state.value,
            "[]",
            EmailProviderName.GMAIL.value,
            NOW.isoformat(),
        ),
    )


def insert_classification(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    is_job_related: bool,
) -> None:
    connection.execute(
        """
        INSERT INTO email_classifications (
            email_id,
            is_job_related,
            category,
            confidence,
            model,
            prompt_version,
            classified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            int(is_job_related),
            "recruiter_outreach" if is_job_related else "other",
            0.9,
            "llama3.1",
            "classification-v1",
            NOW.isoformat(),
        ),
    )
