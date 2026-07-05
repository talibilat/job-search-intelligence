from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from app import models
from app.config import EmailProviderName
from app.db import repositories
from app.db.repositories.base import BaseRepository
from app.models import (
    ApplicationCorrectionRecord,
    ApplicationEventRecord,
    ApplicationRecord,
    ChatMessageRecord,
    EmailConnectionRecord,
    InsightRecord,
    RawEmailRecord,
)
from app.providers.email import EmailAccountRef, EmailAddress, EmailConnection
from app.security import SecretKind, SecretRef
from pydantic import ValidationError


def test_repository_package_exports_phase_zero_stubs() -> None:
    expected_repository_names = [
        "EmailRepository",
        "EmailConnectionRepository",
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
        "EmailConnectionRecord",
        "RawEmailBodyRetentionState",
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
    assert record.body_retention_state is models.RawEmailBodyRetentionState.RETAINED
    assert record.labels == ["Inbox", "Job"]
    assert isinstance(record.sent_at, datetime)


def test_raw_email_record_tracks_retention_states() -> None:
    retention_state = models.RawEmailBodyRetentionState
    base_data = {
        "id": "email-1",
        "thread_id": "thread-1",
        "from_addr": "sender@example.com",
        "to_addr": "me@example.com",
        "subject": "Application received",
        "sent_at": "2026-07-04T10:00:00+00:00",
        "labels": ["Inbox", "Job"],
        "provider": "gmail",
        "ingested_at": "2026-07-04T10:05:00+00:00",
    }

    metadata_only = RawEmailRecord.model_validate(
        base_data
        | {
            "body_text": None,
            "body_retention_state": retention_state.METADATA_ONLY,
        }
    )
    retained = RawEmailRecord.model_validate(
        base_data
        | {
            "body_text": "Thanks for applying.",
            "body_retention_state": retention_state.RETAINED,
        }
    )
    debugging = RawEmailRecord.model_validate(
        base_data
        | {
            "body_text": "Debugging body retained for reconciliation.",
            "body_retention_state": retention_state.DEBUGGING,
        }
    )

    assert metadata_only.body_retention_state is retention_state.METADATA_ONLY
    assert retained.body_retention_state is retention_state.RETAINED
    assert debugging.body_retention_state is retention_state.DEBUGGING
    assert retained.has_retained_body is True
    assert debugging.has_retained_body is True
    assert metadata_only.has_retained_body is False
    assert "Debugging body retained" not in repr(debugging)


def test_raw_email_record_rejects_inconsistent_retention_state() -> None:
    retention_state = models.RawEmailBodyRetentionState
    base_data = {
        "id": "email-1",
        "thread_id": "thread-1",
        "from_addr": "sender@example.com",
        "to_addr": "me@example.com",
        "subject": "Application received",
        "sent_at": "2026-07-04T10:00:00+00:00",
        "labels": ["Inbox", "Job"],
        "provider": "gmail",
        "ingested_at": "2026-07-04T10:05:00+00:00",
    }

    with pytest.raises(ValidationError, match="metadata-only raw emails cannot retain body_text"):
        RawEmailRecord.model_validate(
            base_data
            | {
                "body_text": "Thanks for applying.",
                "body_retention_state": retention_state.METADATA_ONLY,
            }
        )

    with pytest.raises(ValidationError, match="retained raw emails must include body_text"):
        RawEmailRecord.model_validate(
            base_data
            | {
                "body_text": None,
                "body_retention_state": retention_state.RETAINED,
            }
        )

    with pytest.raises(ValidationError):
        RawEmailRecord.model_validate(
            base_data
            | {
                "body_text": None,
                "body_retention_state": "omitted",
            }
        )


def test_application_repository_maps_application_rows() -> None:
    repository = repositories.ApplicationRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            'application-42' AS id,
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
    assert record.id == "application-42"
    assert record.current_status == "applied"
    assert record.manual_lock is False
    assert record.tech_stack == ["Python", "FastAPI"]


def test_event_repository_maps_application_event_rows() -> None:
    repository = repositories.EventRepository(sqlite3.connect(":memory:"))

    record = fetch_required_record(
        repository,
        """
        SELECT
            'event-7' AS id,
            'application-42' AS application_id,
            'email-1' AS email_id,
            'applied' AS event_type,
            '2026-07-01T09:00:00+00:00' AS event_at,
            'confirmation' AS extract_note
        """,
    )

    assert isinstance(record, ApplicationEventRecord)
    assert record.application_id == "application-42"
    assert record.event_type == "applied"
    assert isinstance(record.event_at, datetime)


def test_application_event_record_allows_only_inferred_events_without_email() -> None:
    base_data = {
        "id": "event-7",
        "application_id": "application-42",
        "event_at": "2026-07-01T09:00:00+00:00",
        "extract_note": None,
    }

    inferred_event = ApplicationEventRecord.model_validate(
        base_data | {"email_id": None, "event_type": "ghost_inferred"},
    )
    assert inferred_event.email_id is None

    with pytest.raises(ValidationError, match="ghost-inferred events cannot reference email_id"):
        ApplicationEventRecord.model_validate(
            base_data | {"email_id": "email-1", "event_type": "ghost_inferred"},
        )

    with pytest.raises(ValidationError, match="evidence-backed events require email_id"):
        ApplicationEventRecord.model_validate(
            base_data | {"email_id": None, "event_type": "rejection"},
        )


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
            'application-42' AS application_id,
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


def test_connection_repository_persists_email_connection_metadata() -> None:
    repository = repositories.EmailConnectionRepository(sqlite3.connect(":memory:"))
    repository.execute(
        """
        CREATE TABLE email_connections (
            provider TEXT NOT NULL,
            account_id TEXT NOT NULL,
            display_email TEXT,
            credential_ref_kind TEXT NOT NULL,
            credential_ref_provider TEXT NOT NULL,
            credential_ref_name TEXT NOT NULL,
            granted_scopes TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            credential_expires_at TEXT,
            reauth_required INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (provider, account_id)
        )
        """
    )
    connection = EmailConnection(
        account=EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com"),
        display_email=EmailAddress(address="me@example.com"),
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        connected_at=datetime.fromisoformat("2026-07-05T12:00:00+00:00"),
        credential_expires_at=datetime.fromisoformat("2026-07-05T13:00:00+00:00"),
    )

    saved = repository.save_connection(connection)
    fetched = repository.fetch_connection(connection.account)

    assert isinstance(saved, EmailConnectionRecord)
    assert fetched is not None
    assert fetched.provider == "gmail"
    assert fetched.account_id == "me@example.com"
    assert fetched.credential_ref_name == "me-example-com"
    assert fetched.granted_scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def fetch_required_record[RecordT](
    repository: BaseRepository[RecordT],
    sql: str,
) -> RecordT:
    record = repository.fetch_one(sql)
    assert record is not None
    return record
