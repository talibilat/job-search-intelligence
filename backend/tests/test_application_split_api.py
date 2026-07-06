from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.main import create_app
from app.models.correction import ApplicationSplitNewApplication, ApplicationSplitRequest
from app.services.application_corrections import (
    ApplicationCorrectionService,
    ApplicationSplitConflictError,
    make_manual_split_application_id,
)
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
APPLIED_AT = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
REJECTED_AT = datetime(2026, 7, 3, 17, 30, tzinfo=UTC)
FEEDBACK_AT = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)


def test_post_application_split_moves_events_and_records_audit(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
            extract_note="Role was filled.",
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
            "reason": "The rejection belongs to a separate application.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert new_application_id.startswith("manual-split-")
    assert payload["source_application"]["id"] == "app-merged"
    assert payload["source_application"]["current_status"] == "applied"
    assert payload["source_application"]["manual_lock"] is True
    assert payload["new_application"]["company"] == "Beta Labs"
    assert payload["new_application"]["role_title"] == "Data Engineer"
    assert payload["new_application"]["source"] == "linkedin"
    assert payload["new_application"]["current_status"] == "rejected"
    assert payload["new_application"]["manual_lock"] is True
    assert payload["new_application"]["tech_stack"] == []
    assert payload["moved_events"][0]["id"] == "event-rejected"
    assert payload["moved_events"][0]["application_id"] == new_application_id
    assert payload["correction"]["application_id"] == "app-merged"
    assert payload["correction"]["correction_type"] == "split"
    assert payload["correction"]["before_json"]["source_application"]["id"] == "app-merged"
    assert payload["correction"]["after_json"]["new_application"]["id"] == new_application_id
    assert payload["correction"]["after_json"]["moved_event_ids"] == ["event-rejected"]

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            """
            SELECT current_status, first_seen_at, last_activity_at, manual_lock
            FROM applications
            WHERE id = ?
            """,
            ("app-merged",),
        ).fetchone()
        assert source == ("applied", APPLIED_AT.isoformat(), APPLIED_AT.isoformat(), 1)

        target = db.execute(
            """
            SELECT company, role_title, current_status, manual_lock
            FROM applications
            WHERE id = ?
            """,
            (new_application_id,),
        ).fetchone()
        assert target == ("Beta Labs", "Data Engineer", "rejected", 1)

        reassigned_event = db.execute(
            "SELECT application_id FROM application_events WHERE id = ?",
            ("event-rejected",),
        ).fetchone()
        assert reassigned_event == (new_application_id,)

        corrections = db.execute(
            "SELECT correction_type FROM application_corrections WHERE application_id = ?",
            ("app-merged",),
        ).fetchall()
        assert corrections == [("split",)]


def test_post_application_split_preserves_terminal_status_priority(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_raw_email(connection, "email-feedback")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=FEEDBACK_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-feedback",
            application_id="app-merged",
            email_id="email-feedback",
            event_type="feedback",
            event_at=FEEDBACK_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected", "event-feedback"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert payload["new_application"]["current_status"] == "rejected"

    with sqlite3.connect(database_path) as db:
        target = db.execute(
            "SELECT current_status FROM applications WHERE id = ?",
            (new_application_id,),
        ).fetchone()
        assert target == ("rejected",)


def test_post_application_split_replays_extracted_status_chronologically(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    source_withdrawn_at = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)
    target_applied_at = datetime(2026, 7, 1, 11, 0, tzinfo=UTC)
    target_rejected_at = datetime(2026, 7, 3, 17, 0, tzinfo=UTC)
    target_withdrawn_at = datetime(2026, 7, 5, 10, 0, tzinfo=UTC)
    connection = migrated_connection(database_path)
    try:
        for email_id in (
            "email-source-applied",
            "email-source-rejected",
            "email-source-feedback",
            "email-target-applied",
            "email-target-rejected",
            "email-target-feedback",
        ):
            insert_raw_email(connection, email_id)
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="withdrawn",
            last_activity_at=target_withdrawn_at,
        )
        insert_event(
            connection,
            event_id="event-source-applied",
            application_id="app-merged",
            email_id="email-source-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-source-rejected",
            application_id="app-merged",
            email_id="email-source-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-source-feedback",
            application_id="app-merged",
            email_id="email-source-feedback",
            event_type="feedback",
            event_at=source_withdrawn_at,
            extracted_status="withdrawn",
        )
        insert_event(
            connection,
            event_id="event-target-applied",
            application_id="app-merged",
            email_id="email-target-applied",
            event_type="applied",
            event_at=target_applied_at,
        )
        insert_event(
            connection,
            event_id="event-target-rejected",
            application_id="app-merged",
            email_id="email-target-rejected",
            event_type="rejection",
            event_at=target_rejected_at,
        )
        insert_event(
            connection,
            event_id="event-target-feedback",
            application_id="app-merged",
            email_id="email-target-feedback",
            event_type="feedback",
            event_at=target_withdrawn_at,
            extracted_status="withdrawn",
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": [
                "event-target-applied",
                "event-target-rejected",
                "event-target-feedback",
            ],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert payload["source_application"]["current_status"] == "withdrawn"
    assert payload["new_application"]["current_status"] == "withdrawn"

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            "SELECT current_status FROM applications WHERE id = ?",
            ("app-merged",),
        ).fetchone()
        assert source == ("withdrawn",)

        target = db.execute(
            "SELECT current_status FROM applications WHERE id = ?",
            (new_application_id,),
        ).fetchone()
        assert target == ("withdrawn",)


def test_post_application_split_orders_selected_events_like_application_timeline(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    shared_event_at = datetime(2026, 7, 3, 17, 0, tzinfo=UTC)
    selected_rejected_sent_at = datetime(2026, 7, 3, 17, 1, tzinfo=UTC)
    selected_feedback_sent_at = datetime(2026, 7, 3, 17, 2, tzinfo=UTC)
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-source-applied")
        insert_raw_email(
            connection,
            "email-selected-rejected",
            sent_at=selected_rejected_sent_at,
        )
        insert_raw_email(
            connection,
            "email-selected-feedback",
            sent_at=selected_feedback_sent_at,
        )
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="withdrawn",
            last_activity_at=shared_event_at,
        )
        insert_event(
            connection,
            event_id="event-source-applied",
            application_id="app-merged",
            email_id="email-source-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-a-selected-feedback",
            application_id="app-merged",
            email_id="email-selected-feedback",
            event_type="feedback",
            event_at=shared_event_at,
            extracted_status="withdrawn",
        )
        insert_event(
            connection,
            event_id="event-z-selected-rejected",
            application_id="app-merged",
            email_id="email-selected-rejected",
            event_type="rejection",
            event_at=shared_event_at,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": [
                "event-a-selected-feedback",
                "event-z-selected-rejected",
            ],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert payload["new_application"]["current_status"] == "withdrawn"
    assert [event["id"] for event in payload["moved_events"]] == [
        "event-z-selected-rejected",
        "event-a-selected-feedback",
    ]

    with sqlite3.connect(database_path) as db:
        target = db.execute(
            "SELECT current_status FROM applications WHERE id = ?",
            (new_application_id,),
        ).fetchone()
        assert target == ("withdrawn",)


def test_post_application_split_preserves_locked_source_status(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="withdrawn",
            last_activity_at=REJECTED_AT,
            manual_lock=True,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_application"]["current_status"] == "withdrawn"
    assert payload["source_application"]["manual_lock"] is True

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            """
            SELECT current_status, first_seen_at, last_activity_at, manual_lock
            FROM applications
            WHERE id = ?
            """,
            ("app-merged",),
        ).fetchone()
        assert source == (
            "withdrawn",
            APPLIED_AT.isoformat(),
            APPLIED_AT.isoformat(),
            1,
        )


def test_post_application_split_preserves_target_segmentation_fields(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
                "salary_min": 120000,
                "salary_max": 150000,
                "currency": "USD",
                "location": "New York, NY",
                "work_mode": "hybrid",
                "seniority": "senior",
                "sponsorship": "offered",
                "tech_stack": ["Python", "FastAPI"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    new_application_id = payload["new_application"]["id"]
    assert payload["new_application"]["salary_min"] == 120000
    assert payload["new_application"]["salary_max"] == 150000
    assert payload["new_application"]["currency"] == "USD"
    assert payload["new_application"]["location"] == "New York, NY"
    assert payload["new_application"]["work_mode"] == "hybrid"
    assert payload["new_application"]["seniority"] == "senior"
    assert payload["new_application"]["sponsorship"] == "offered"
    assert payload["new_application"]["tech_stack"] == ["Python", "FastAPI"]

    with sqlite3.connect(database_path) as db:
        target = db.execute(
            """
            SELECT salary_min, salary_max, currency, location, work_mode,
                   seniority, sponsorship, tech_stack
            FROM applications
            WHERE id = ?
            """,
            (new_application_id,),
        ).fetchone()
        assert target == (
            120000,
            150000,
            "USD",
            "New York, NY",
            "hybrid",
            "senior",
            "offered",
            '["Python","FastAPI"]',
        )


def test_post_application_split_persists_corrected_source_segmentation_fields(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Moved Facts Corp",
            role_title="Moved Role",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "source_application": {
                "company": "Acme Corp",
                "role_title": "Software Engineer",
                "source": "company_site",
                "salary_min": 90000,
                "salary_max": 110000,
                "currency": "USD",
                "location": "Austin, TX",
                "work_mode": "remote",
                "seniority": "mid",
                "sponsorship": "not_offered",
                "tech_stack": ["TypeScript", "React"],
            },
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_application"]["company"] == "Acme Corp"
    assert payload["source_application"]["role_title"] == "Software Engineer"
    assert payload["source_application"]["source"] == "company_site"
    assert payload["source_application"]["salary_min"] == 90000
    assert payload["source_application"]["salary_max"] == 110000
    assert payload["source_application"]["currency"] == "USD"
    assert payload["source_application"]["location"] == "Austin, TX"
    assert payload["source_application"]["work_mode"] == "remote"
    assert payload["source_application"]["seniority"] == "mid"
    assert payload["source_application"]["sponsorship"] == "not_offered"
    assert payload["source_application"]["tech_stack"] == ["TypeScript", "React"]

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            """
            SELECT company, role_title, source, salary_min, salary_max, currency,
                   location, work_mode, seniority, sponsorship, tech_stack,
                   current_status, first_seen_at, last_activity_at
            FROM applications
            WHERE id = ?
            """,
            ("app-merged",),
        ).fetchone()
        assert source == (
            "Acme Corp",
            "Software Engineer",
            "company_site",
            90000,
            110000,
            "USD",
            "Austin, TX",
            "remote",
            "mid",
            "not_offered",
            '["TypeScript","React"]',
            "applied",
            APPLIED_AT.isoformat(),
            APPLIED_AT.isoformat(),
        )


def test_post_application_split_preserves_omitted_source_segmentation_fields(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Moved Facts Corp",
            role_title="Moved Role",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        connection.execute(
            """
            UPDATE applications
            SET salary_min = ?, salary_max = ?, currency = ?, location = ?,
                work_mode = ?, seniority = ?, sponsorship = ?, tech_stack = ?
            WHERE id = ?
            """,
            (
                90000,
                110000,
                "USD",
                "Austin, TX",
                "remote",
                "mid",
                "not_offered",
                '["TypeScript","React"]',
                "app-merged",
            ),
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.post(
        "/applications/app-merged/split",
        json={
            "event_ids": ["event-rejected"],
            "source_application": {
                "company": "Acme Corp",
                "role_title": "Software Engineer",
            },
            "new_application": {
                "company": "Beta Labs",
                "role_title": "Data Engineer",
                "source": "linkedin",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_application"]["company"] == "Acme Corp"
    assert payload["source_application"]["role_title"] == "Software Engineer"
    assert payload["source_application"]["source"] == "other"
    assert payload["source_application"]["salary_min"] == 90000
    assert payload["source_application"]["salary_max"] == 110000
    assert payload["source_application"]["currency"] == "USD"
    assert payload["source_application"]["location"] == "Austin, TX"
    assert payload["source_application"]["work_mode"] == "remote"
    assert payload["source_application"]["seniority"] == "mid"
    assert payload["source_application"]["sponsorship"] == "not_offered"
    assert payload["source_application"]["tech_stack"] == ["TypeScript", "React"]

    with sqlite3.connect(database_path) as db:
        source = db.execute(
            """
            SELECT company, role_title, source, salary_min, salary_max, currency,
                   location, work_mode, seniority, sponsorship, tech_stack
            FROM applications
            WHERE id = ?
            """,
            ("app-merged",),
        ).fetchone()
        assert source == (
            "Acme Corp",
            "Software Engineer",
            "other",
            90000,
            110000,
            "USD",
            "Austin, TX",
            "remote",
            "mid",
            "not_offered",
            '["TypeScript","React"]',
        )


def test_application_split_rejects_repositories_with_different_connections(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    setup_connection = migrated_connection(database_path)
    try:
        insert_raw_email(setup_connection, "email-applied")
        insert_raw_email(setup_connection, "email-rejected")
        insert_application(
            setup_connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            setup_connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            setup_connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        setup_connection.commit()
    finally:
        setup_connection.close()

    application_connection = sqlite3.connect(database_path)
    event_connection = sqlite3.connect(database_path)
    correction_connection = sqlite3.connect(database_path)
    try:
        service = ApplicationCorrectionService(
            application_repository=ApplicationRepository(application_connection),
            event_repository=EventRepository(event_connection),
            correction_repository=CorrectionRepository(correction_connection),
        )

        with pytest.raises(
            ApplicationSplitConflictError,
            match="Manual split repositories must share one SQLite connection.",
        ):
            service.split_application(
                application_id="app-merged",
                request=ApplicationSplitRequest(
                    event_ids=["event-rejected"],
                    new_application=ApplicationSplitNewApplication(
                        company="Beta Labs",
                        role_title="Data Engineer",
                        source="linkedin",
                    ),
                ),
            )

        with sqlite3.connect(database_path) as db:
            assert db.execute(
                "SELECT COUNT(*) FROM applications WHERE id LIKE 'manual-split-%'",
            ).fetchone() == (0,)
            assert db.execute(
                "SELECT application_id FROM application_events WHERE id = ?",
                ("event-rejected",),
            ).fetchone() == ("app-merged",)
            assert db.execute(
                "SELECT COUNT(*) FROM application_corrections",
            ).fetchone() == (0,)
    finally:
        application_connection.close()
        event_connection.close()
        correction_connection.close()


def test_application_split_rejects_refused_target_upsert_before_moving_events(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    selected_event_ids = ["event-rejected"]
    new_application_id = make_manual_split_application_id(
        source_application_id="app-merged",
        event_ids=selected_event_ids,
    )
    connection = migrated_connection(database_path)
    try:
        insert_raw_email(connection, "email-applied")
        insert_raw_email(connection, "email-rejected")
        insert_application(
            connection,
            application_id="app-merged",
            company="Acme Corp",
            role_title="Software Engineer",
            first_seen_at=APPLIED_AT,
            current_status="rejected",
            last_activity_at=REJECTED_AT,
        )
        insert_event(
            connection,
            event_id="event-applied",
            application_id="app-merged",
            email_id="email-applied",
            event_type="applied",
            event_at=APPLIED_AT,
        )
        insert_event(
            connection,
            event_id="event-rejected",
            application_id="app-merged",
            email_id="email-rejected",
            event_type="rejection",
            event_at=REJECTED_AT,
        )
        insert_merge_source_correction(connection, deleted_source_application_id=new_application_id)
        connection.commit()

        service = ApplicationCorrectionService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            correction_repository=CorrectionRepository(connection),
        )

        with pytest.raises(
            ApplicationSplitConflictError,
            match="Split target application could not be created.",
        ):
            service.split_application(
                application_id="app-merged",
                request=ApplicationSplitRequest(
                    event_ids=selected_event_ids,
                    new_application=ApplicationSplitNewApplication(
                        company="Beta Labs",
                        role_title="Data Engineer",
                        source="linkedin",
                    ),
                ),
            )

        assert (
            connection.execute(
                "SELECT COUNT(*) FROM applications WHERE id = ?",
                (new_application_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT application_id FROM application_events WHERE id = ?",
                ("event-rejected",),
            ).fetchone()[0]
            == "app-merged"
        )
    finally:
        connection.close()


def migrated_connection(database_path: Path) -> sqlite3.Connection:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    connection = sqlite3.connect(str(database_path))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    sent_at: datetime = NOW,
) -> None:
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
            "Application update",
            sent_at.isoformat(),
            "Synthetic job-search email body.",
            "retained",
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def insert_merge_source_correction(
    connection: sqlite3.Connection,
    *,
    deleted_source_application_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO application_corrections (
            application_id, correction_type, before_json, after_json, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "app-merged",
            "merge",
            "{}",
            f'{{"deleted_source_application_id":"{deleted_source_application_id}"}}',
            "Existing merge source marker.",
            NOW.isoformat(),
        ),
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str,
    role_title: str,
    first_seen_at: datetime,
    current_status: str,
    last_activity_at: datetime,
    manual_lock: bool = False,
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at,
            current_status, salary_min, salary_max, currency,
            location, work_mode, seniority, sponsorship, tech_stack,
            last_activity_at, manual_lock, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            company,
            role_title,
            "other",
            first_seen_at.isoformat(),
            current_status,
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            "[]",
            last_activity_at.isoformat(),
            int(manual_lock),
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )


def insert_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    application_id: str,
    email_id: str,
    event_type: str,
    event_at: datetime,
    extract_note: str | None = None,
    extracted_status: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at, extract_note, extracted_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            application_id,
            email_id,
            event_type,
            event_at.isoformat(),
            extract_note,
            extracted_status,
        ),
    )
