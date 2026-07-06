from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.services.application_corrections import (
    ApplicationCorrectionService,
    ApplicationCorrectionServiceError,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)
APPLIED_AT = "2026-07-01T09:00:00+00:00"


def test_reset_application_lock_clears_lock_audits_and_allows_automatic_update(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_application(
        connection,
        application_id="app-1",
        current_status="withdrawn",
        manual_lock=True,
    )
    connection.commit()

    result = make_service(connection).reset_application_lock(
        application_id="app-1",
        reason="Let aggregation manage this application again.",
    )

    assert result.application.id == "app-1"
    assert result.application.manual_lock is False
    assert result.application.updated_at == NOW
    assert result.correction.application_id == "app-1"
    assert result.correction.correction_type == "reset_lock"
    assert result.correction.reason == "Let aggregation manage this application again."
    before_application = cast(dict[str, object], result.correction.before_json["application"])
    after_application = cast(dict[str, object], result.correction.after_json["application"])
    assert before_application["manual_lock"] is True
    assert after_application["manual_lock"] is False

    outcome = ApplicationRepository(connection).upsert_application(
        id="app-1",
        company="Acme Corp",
        role_title="Software Engineer",
        source="other",
        first_seen_at=APPLIED_AT,
        current_status="offer",
        last_activity_at="2026-07-08T09:00:00+00:00",
        created_at=APPLIED_AT,
        updated_at="2026-07-08T09:00:00+00:00",
    )
    stored = ApplicationRepository(connection).get_application("app-1")

    assert outcome == "upserted"
    assert stored is not None
    assert stored.current_status == "offer"
    assert stored.manual_lock is False


def test_reset_application_lock_rejects_unlocked_application(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_application(
        connection,
        application_id="app-1",
        current_status="applied",
        manual_lock=False,
    )
    connection.commit()

    with pytest.raises(ApplicationCorrectionServiceError):
        make_service(connection).reset_application_lock(
            application_id="app-1",
            reason="No lock is active.",
        )


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(str(database_path))


def make_service(connection: sqlite3.Connection) -> ApplicationCorrectionService:
    return ApplicationCorrectionService(
        application_repository=ApplicationRepository(connection),
        event_repository=EventRepository(connection),
        correction_repository=CorrectionRepository(connection),
        clock=lambda: NOW,
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    current_status: str,
    manual_lock: bool,
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
            "Acme Corp",
            "Software Engineer",
            "other",
            APPLIED_AT,
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            json.dumps([]),
            APPLIED_AT,
            int(manual_lock),
            APPLIED_AT,
            APPLIED_AT,
        ),
    )
