from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.services.manual_merge import (
    ManualApplicationMergeService,
    ManualMergeInvalidRequestError,
    ManualMergeNotFoundError,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)


def test_manual_merge_moves_source_events_and_audits_correction(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "target-email")
    insert_raw_email(connection, "source-email")
    insert_application(
        connection,
        application_id="app-target",
        company="Acme Corp",
        role_title="Software Engineer",
        current_status="applied",
        first_seen_at="2026-07-01T09:00:00+00:00",
        last_activity_at="2026-07-01T09:00:00+00:00",
        tech_stack=["Python"],
    )
    insert_application(
        connection,
        application_id="app-source",
        company="Acme Corporation",
        role_title="Backend Engineer",
        current_status="rejected",
        first_seen_at="2026-07-03T10:00:00+00:00",
        last_activity_at="2026-07-05T10:00:00+00:00",
        tech_stack=["Python", "FastAPI"],
    )
    insert_event(
        connection,
        event_id="event-target-applied",
        application_id="app-target",
        email_id="target-email",
        event_type="applied",
        event_at="2026-07-01T09:00:00+00:00",
    )
    insert_event(
        connection,
        event_id="event-source-rejection",
        application_id="app-source",
        email_id="source-email",
        event_type="rejection",
        event_at="2026-07-05T10:00:00+00:00",
    )
    insert_correction(
        connection,
        application_id="app-source",
        correction_type="status_edit",
        before_json={"current_status": "applied"},
        after_json={"current_status": "rejected"},
    )
    connection.commit()

    service = make_service(connection)
    result = service.merge_applications(
        target_application_id="app-target",
        source_application_id="app-source",
        reason="Duplicate application reconstructed from separate threads.",
    )

    assert result.target_application_id == "app-target"
    assert result.source_application_id == "app-source"
    assert result.moved_event_count == 1
    assert result.application.id == "app-target"
    assert result.application.current_status == "rejected"
    assert result.application.first_seen_at == datetime(2026, 7, 1, 9, tzinfo=UTC)
    assert result.application.last_activity_at == datetime(2026, 7, 5, 10, tzinfo=UTC)
    assert result.application.tech_stack == ["Python", "FastAPI"]
    assert result.application.manual_lock is True
    assert result.correction.application_id == "app-target"
    assert result.correction.correction_type == "merge"
    assert result.correction.reason == "Duplicate application reconstructed from separate threads."

    source_row = connection.execute(
        "SELECT COUNT(*) FROM applications WHERE id = 'app-source'",
    ).fetchone()
    assert source_row is not None
    assert tuple(source_row) == (0,)

    events = connection.execute(
        """
        SELECT id, application_id, email_id, event_type
        FROM application_events
        ORDER BY event_at
        """,
    ).fetchall()
    assert [tuple(row) for row in events] == [
        ("event-target-applied", "app-target", "target-email", "applied"),
        ("event-source-rejection", "app-target", "source-email", "rejection"),
    ]

    correction_rows = connection.execute(
        """
        SELECT application_id, correction_type, before_json, after_json, id
        FROM application_corrections
        WHERE application_id = 'app-target'
        ORDER BY id
        """,
    ).fetchall()
    assert [tuple(row[:2]) for row in correction_rows] == [
        ("app-target", "status_edit"),
        ("app-target", "merge"),
    ]
    before_json = json.loads(correction_rows[1][2])
    after_json = json.loads(correction_rows[1][3])
    assert before_json["target_application"]["id"] == "app-target"
    assert before_json["source_application"]["id"] == "app-source"
    assert before_json["source_events"][0]["id"] == "event-source-rejection"
    assert before_json["source_corrections"][0]["application_id"] == "app-source"
    assert before_json["source_corrections"][0]["correction_type"] == "status_edit"
    assert after_json["target_application"]["id"] == "app-target"
    assert after_json["deleted_source_application_id"] == "app-source"
    assert after_json["moved_event_ids"] == ["event-source-rejection"]
    assert after_json["moved_correction_ids"] == [correction_rows[0][4]]


def test_manual_merge_rejects_merging_application_into_itself(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_application(connection, application_id="app-target")
    connection.commit()

    service = make_service(connection)

    with pytest.raises(ManualMergeInvalidRequestError):
        service.merge_applications(
            target_application_id="app-target",
            source_application_id="app-target",
            reason=None,
        )


def test_manual_merge_lock_blocks_later_upsert_from_recreating_duplicate(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_application(
        connection,
        application_id="app-target",
        current_status="applied",
    )
    insert_application(
        connection,
        application_id="app-source",
        current_status="rejected",
        last_activity_at="2026-07-05T10:00:00+00:00",
    )
    connection.commit()

    service = make_service(connection)
    service.merge_applications(
        target_application_id="app-target",
        source_application_id="app-source",
        reason="Duplicate application.",
    )

    application_repository = ApplicationRepository(connection)
    target_changed = application_repository.upsert_application(
        id="app-target",
        company="Changed Corp",
        role_title="Changed Role",
        source="other",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="offer",
        last_activity_at="2026-07-06T10:00:00+00:00",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        tech_stack=["Go"],
    )
    source_recreated = application_repository.upsert_application(
        id="app-source",
        company="Acme Corp",
        role_title="Software Engineer",
        source="other",
        first_seen_at="2026-07-03T10:00:00+00:00",
        current_status="rejected",
        last_activity_at="2026-07-05T10:00:00+00:00",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )

    assert target_changed == "manual_conflict"
    assert source_recreated == "merged_source"
    target = application_repository.get_application("app-target")
    assert target is not None
    assert target.company == "Acme Corp"
    assert target.current_status == "rejected"
    assert target.tech_stack == []
    assert application_repository.get_application("app-source") is None


def test_manual_merge_reports_missing_source_application(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_application(connection, application_id="app-target")
    connection.commit()

    service = make_service(connection)

    with pytest.raises(ManualMergeNotFoundError) as error_info:
        service.merge_applications(
            target_application_id="app-target",
            source_application_id="missing-source",
            reason=None,
        )

    assert error_info.value.application_id == "missing-source"


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(str(database_path))


def make_service(connection: sqlite3.Connection) -> ManualApplicationMergeService:
    return ManualApplicationMergeService(
        application_repository=ApplicationRepository(connection),
        event_repository=EventRepository(connection),
        correction_repository=CorrectionRepository(connection),
        clock=lambda: NOW,
    )


def insert_raw_email(connection: sqlite3.Connection, email_id: str) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject,
            sent_at, body_text, body_retention_state, labels,
            provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "me@example.test",
            "Job update",
            NOW.isoformat(),
            "Test body content.",
            "retained",
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str = "Acme Corp",
    role_title: str = "Software Engineer",
    current_status: str = "applied",
    first_seen_at: str = "2026-07-01T09:00:00+00:00",
    last_activity_at: str = "2026-07-01T09:00:00+00:00",
    tech_stack: list[str] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at,
            current_status, salary_min, salary_max, currency,
            location, work_mode, seniority, sponsorship,
            tech_stack, last_activity_at, manual_lock,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            company,
            role_title,
            "other",
            first_seen_at,
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            json.dumps(tech_stack or []),
            last_activity_at,
            0,
            first_seen_at,
            first_seen_at,
        ),
    )


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    email_id: str,
    event_type: str,
    event_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at, extract_note
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, application_id, email_id, event_type, event_at, None),
    )


def insert_correction(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    correction_type: str,
    before_json: dict[str, object],
    after_json: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO application_corrections (
            application_id, correction_type, before_json,
            after_json, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            correction_type,
            json.dumps(before_json),
            json.dumps(after_json),
            "Previous manual correction.",
            NOW.isoformat(),
        ),
    )
