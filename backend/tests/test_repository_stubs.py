from __future__ import annotations

import sqlite3
from datetime import datetime

from app import models
from app.db import repositories
from app.db.repositories.base import BaseRepository
from app.models import (
    ApplicationCorrectionRecord,
    ApplicationEventRecord,
    ApplicationRecord,
    ChatMessageRecord,
    InsightRecord,
    RawEmailRecord,
)


def test_repository_package_exports_phase_zero_stubs() -> None:
    expected_repository_names = [
        "EmailRepository",
        "ApplicationRepository",
        "EventRepository",
        "InsightRepository",
        "CorrectionRepository",
        "ChatRepository",
    ]

    for name in expected_repository_names:
        repository_class = getattr(repositories, name, None)
        assert isinstance(repository_class, type), name
        assert issubclass(repository_class, BaseRepository), name


def test_model_package_exports_repository_record_dtos() -> None:
    expected_model_names = [
        "RawEmailRecord",
        "ApplicationRecord",
        "ApplicationEventRecord",
        "InsightRecord",
        "ApplicationCorrectionRecord",
        "ChatMessageRecord",
    ]

    for name in expected_model_names:
        assert isinstance(getattr(models, name, None), type), name


def test_email_repository_maps_raw_email_rows() -> None:
    repository = repositories.EmailRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            'email-1' AS id,
            'thread-1' AS thread_id,
            'sender@example.com' AS from_addr,
            'me@example.com' AS to_addr,
            'Application received' AS subject,
            '2026-07-04T10:00:00+00:00' AS sent_at,
            'Thanks for applying.' AS body_text,
            'retained' AS body_retention_state,
            '["Inbox", "Job"]' AS labels,
            'gmail' AS provider,
            '2026-07-04T10:05:00+00:00' AS ingested_at
        """,
    )

    assert isinstance(record, RawEmailRecord)
    assert record.id == "email-1"
    assert record.labels == ["Inbox", "Job"]
    assert isinstance(record.sent_at, datetime)


def test_application_repository_maps_application_rows() -> None:
    repository = repositories.ApplicationRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            42 AS id,
            'Acme' AS company,
            'Software Engineer' AS role_title,
            'linkedin' AS source,
            '2026-07-01T09:00:00+00:00' AS first_seen_at,
            'applied' AS current_status,
            100000 AS salary_min,
            120000 AS salary_max,
            'USD' AS currency,
            'Remote' AS location,
            'remote' AS work_mode,
            'senior' AS seniority,
            'unknown' AS sponsorship,
            '["Python", "FastAPI"]' AS tech_stack,
            '2026-07-02T09:00:00+00:00' AS last_activity_at,
            0 AS manual_lock,
            '2026-07-01T09:01:00+00:00' AS created_at,
            '2026-07-02T09:01:00+00:00' AS updated_at
        """,
    )

    assert isinstance(record, ApplicationRecord)
    assert record.id == 42
    assert record.current_status == "applied"
    assert record.manual_lock is False
    assert record.tech_stack == ["Python", "FastAPI"]


def test_event_repository_maps_application_event_rows() -> None:
    repository = repositories.EventRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            7 AS id,
            42 AS application_id,
            'email-1' AS email_id,
            'applied' AS event_type,
            '2026-07-01T09:00:00+00:00' AS event_at,
            'confirmation' AS extract_note
        """,
    )

    assert isinstance(record, ApplicationEventRecord)
    assert record.application_id == 42
    assert record.event_type == "applied"
    assert isinstance(record.event_at, datetime)


def test_insight_repository_maps_insight_rows() -> None:
    repository = repositories.InsightRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            3 AS id,
            'story' AS type,
            'Your search is trending toward backend roles.' AS content,
            'hash-1' AS inputs_hash,
            1 AS is_stale,
            'gpt-4.1' AS model,
            '2026-07-04T11:00:00+00:00' AS generated_at
        """,
    )

    assert isinstance(record, InsightRecord)
    assert record.type == "story"
    assert record.is_stale is True


def test_correction_repository_maps_application_correction_rows() -> None:
    repository = repositories.CorrectionRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            2 AS id,
            42 AS application_id,
            'status_edit' AS correction_type,
            '{"current_status": "applied"}' AS before_json,
            '{"current_status": "rejected"}' AS after_json,
            'manual audit' AS reason,
            '2026-07-04T12:00:00+00:00' AS created_at
        """,
    )

    assert isinstance(record, ApplicationCorrectionRecord)
    assert record.correction_type == "status_edit"
    assert record.before_json == {"current_status": "applied"}
    assert record.after_json == {"current_status": "rejected"}


def test_chat_repository_maps_chat_message_rows() -> None:
    repository = repositories.ChatRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            5 AS id,
            'conversation-1' AS conversation_id,
            'assistant' AS role,
            'You have one overdue follow-up.' AS content,
            '[{"email_id": "email-1"}]' AS citations_json,
            '[{"tool": "structured_query"}]' AS tool_outputs_json,
            '2026-07-04T13:00:00+00:00' AS created_at
        """,
    )

    assert isinstance(record, ChatMessageRecord)
    assert record.conversation_id == "conversation-1"
    assert record.citations_json == [{"email_id": "email-1"}]
    assert record.tool_outputs_json == [{"tool": "structured_query"}]


def fetch_required_record[RecordT](
    repository: BaseRepository[RecordT],
    sql: str,
) -> RecordT:
    record = repository.fetch_one(sql)
    assert record is not None
    return record
