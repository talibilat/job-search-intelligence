from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import (
    ApplicationRepository,
    CorrectionConflictRepository,
    EmailRepository,
    EventRepository,
    MetricsRepository,
)
from app.models.application import ApplicationStatus, SponsorshipStatus, WorkMode
from app.models.classification import EmailClassificationRecord, JobEmailCategory
from app.models.event import ApplicationEventType
from app.pipeline.classify import AcceptedLLMExtraction, JobApplicationExtraction
from app.services.aggregation import AggregationService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
EVENT_AT = datetime(2026, 7, 4, 12, 30, tzinfo=UTC)


def test_aggregation_creates_one_application_from_single_extraction(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    service = make_service(connection)
    result = service.run([extraction])

    assert result.extraction_count == 1
    assert result.applications_upserted == 1
    assert result.events_upserted == 1
    assert result.skipped_not_job_related == 0

    stored_apps = connection.execute(
        "SELECT company, role_title, current_status, source FROM applications",
    ).fetchall()
    assert len(stored_apps) == 1
    assert tuple(stored_apps[0]) == ("Acme Corp", "Software Engineer", "applied", "other")

    stored_events = connection.execute(
        "SELECT event_type, email_id FROM application_events",
    ).fetchall()
    assert len(stored_events) == 1
    assert tuple(stored_events[0]) == ("applied", "email-1")


def test_aggregation_groups_multiple_extractions_into_one_application(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    extraction_1 = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    extraction_2 = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Senior Software Engineer",
        status="rejected",
        event_type="rejection",
        event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        rejection_reason="Position filled",
    )
    service = make_service(connection)
    result = service.run([extraction_1, extraction_2])

    assert result.extraction_count == 2
    assert result.applications_upserted == 1
    assert result.events_upserted == 2
    assert result.skipped_not_job_related == 0

    stored_apps = connection.execute(
        "SELECT company, role_title, current_status FROM applications",
    ).fetchall()
    assert len(stored_apps) == 1
    assert tuple(stored_apps[0]) == ("Acme Corp", "Software Engineer", "rejected")

    stored_events = connection.execute(
        "SELECT event_type, email_id, extract_note FROM application_events ORDER BY event_at",
    ).fetchall()
    assert len(stored_events) == 2
    assert tuple(stored_events[0]) == ("applied", "email-1", None)
    assert tuple(stored_events[1]) == ("rejection", "email-2", "Position filled")


def test_status_derivation_uses_latest_event_in_timeline(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    offer = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.OFFER,
        status="offer",
        event_type="offer",
        event_at=datetime(2026, 7, 9, 10, 0, tzinfo=UTC),
    )
    rejection = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.REJECTION,
        status="rejected",
        event_type="rejection",
        event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
    )

    make_service(connection).run([offer, rejection])

    assert_current_status(connection, "rejected")


def test_status_derivation_includes_existing_event_history(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    service = make_service(connection)
    service.run(
        [
            make_extraction(
                email_id="email-1",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.OFFER,
                status="offer",
                event_type="offer",
                event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
            ),
        ],
    )
    service.run(
        [
            make_extraction(
                email_id="email-2",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.REJECTION,
                status="rejected",
                event_type="rejection",
                event_at=datetime(2026, 7, 9, 10, 0, tzinfo=UTC),
            ),
        ],
    )

    assert_current_status(connection, "offer")


def test_follow_up_email_alone_does_not_create_a_submitted_application(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    service = make_service(connection)
    result = service.run(
        [
            make_extraction(
                email_id="email-1",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.FOLLOW_UP,
                status="interview",
                event_type="feedback",
                event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
            ),
        ],
    )
    assert result.applications_upserted == 0
    assert result.events_upserted == 0
    assert result.skipped_not_job_related == 0
    assert result.skipped_non_application_email_count == 1
    assert connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0


def test_general_job_emails_never_create_applications_on_rerun(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    categories = (
        JobEmailCategory.RECRUITER_OUTREACH,
        JobEmailCategory.FOLLOW_UP,
        JobEmailCategory.OTHER,
    )
    extractions = []
    for index, category in enumerate(categories):
        email_id = f"general-job-email-{index}"
        insert_raw_email(connection, email_id, thread_id=f"thread-{index}")
        extractions.append(
            make_extraction(
                email_id=email_id,
                category=category,
                status=None,
                event_type=None,
            )
        )
    connection.commit()
    service = make_service(connection)

    first = service.run(extractions)
    second = service.run(extractions)

    assert first.skipped_non_application_email_count == 3
    assert second.skipped_non_application_email_count == 3
    assert connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0] == 0


def test_status_derivation_tiebreaks_same_event_at_by_email_sent_at(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    shared_event_at = datetime(2026, 7, 5, 9, 0, tzinfo=UTC)
    insert_raw_email(
        connection,
        "email-offer",
        thread_id="thread-abc",
        sent_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )
    insert_raw_email(
        connection,
        "email-rejection",
        thread_id="thread-abc",
        sent_at=datetime(2026, 7, 5, 11, 0, tzinfo=UTC),
    )
    connection.commit()

    make_service(connection).run(
        [
            make_extraction(
                email_id="email-rejection",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.REJECTION,
                status="rejected",
                event_type="rejection",
                event_at=shared_event_at,
            ),
            make_extraction(
                email_id="email-offer",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.OFFER,
                status="offer",
                event_type="offer",
                event_at=shared_event_at,
            ),
        ],
    )

    assert_current_status(connection, "rejected")


def test_status_derivation_tiebreaks_same_event_and_sent_at_by_classified_at(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    shared_event_at = datetime(2026, 7, 5, 9, 0, tzinfo=UTC)
    shared_sent_at = datetime(2026, 7, 5, 10, 0, tzinfo=UTC)
    insert_raw_email(connection, "email-offer", thread_id="thread-abc", sent_at=shared_sent_at)
    insert_raw_email(
        connection,
        "email-rejection",
        thread_id="thread-abc",
        sent_at=shared_sent_at,
    )
    connection.commit()

    make_service(connection).run(
        [
            make_extraction(
                email_id="email-rejection",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.REJECTION,
                status="rejected",
                event_type="rejection",
                event_at=shared_event_at,
                classified_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
            ),
            make_extraction(
                email_id="email-offer",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.OFFER,
                status="offer",
                event_type="offer",
                event_at=shared_event_at,
                classified_at=datetime(2026, 7, 5, 11, 0, tzinfo=UTC),
            ),
        ],
    )

    assert_current_status(connection, "rejected")


def test_manual_locked_status_is_not_automatically_overwritten(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    service = make_service(connection)
    service.run(
        [
            make_extraction(
                email_id="email-1",
                company="Acme Corp",
                role_title="Software Engineer",
                status="applied",
                event_type="applied",
                event_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
            ),
        ],
    )
    connection.execute(
        "UPDATE applications SET current_status = 'withdrawn', manual_lock = 1",
    )
    connection.commit()

    service.run(
        [
            make_extraction(
                email_id="email-2",
                company="Acme Corp",
                role_title="Software Engineer",
                category=JobEmailCategory.REJECTION,
                status="rejected",
                event_type="rejection",
                event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
            ),
        ],
    )

    assert_current_status(connection, "withdrawn")


def test_status_derivation_uses_event_type_when_status_is_missing(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.INTERVIEW_INVITE,
        status=None,
        event_type="interview_scheduled",
        event_at=EVENT_AT,
    )

    make_service(connection).run([extraction])

    assert_current_status(connection, "interview")


def test_grouping_key_uses_email_sent_at_when_event_at_missing_without_thread(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(
        connection,
        "email-1",
        thread_id=None,
        sent_at=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )
    insert_raw_email(
        connection,
        "email-2",
        thread_id=None,
        sent_at=datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
    )
    connection.commit()

    service = make_service(connection)
    result = service.run(
        [
            make_extraction(
                email_id="email-1",
                company="Acme Corp",
                role_title="Software Engineer",
                status="applied",
                event_type="applied",
                event_at=None,
            ),
            make_extraction(
                email_id="email-2",
                company="Acme Corp",
                role_title="Software Engineer",
                status="applied",
                event_type="applied",
                event_at=None,
            ),
        ],
    )

    stored_apps = connection.execute("SELECT COUNT(*) FROM applications").fetchone()
    assert stored_apps is not None
    assert result.applications_upserted == 2
    assert stored_apps[0] == 2


def test_aggregation_is_idempotent(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    service = make_service(connection)

    result_1 = service.run([extraction])
    result_2 = service.run([extraction])

    assert result_1.applications_upserted == 1
    assert result_1.events_upserted == 1
    assert result_2.applications_upserted == 1
    assert result_2.events_upserted == 1

    stored_apps = connection.execute("SELECT COUNT(*) FROM applications").fetchone()
    stored_events = connection.execute(
        "SELECT COUNT(*) FROM application_events",
    ).fetchone()

    assert stored_apps is not None
    assert stored_apps[0] == 1
    assert stored_events is not None
    assert stored_events[0] == 1


def test_aggregation_full_rerun_keeps_one_application_and_timeline_events(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    extraction_1 = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    extraction_2 = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.REJECTION,
        status="rejected",
        event_type="rejection",
        event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        rejection_reason="Position filled",
    )
    service = make_service(connection)

    service.run([extraction_1, extraction_2])
    first_application_ids = connection.execute(
        "SELECT id FROM applications ORDER BY id",
    ).fetchall()
    first_events = connection.execute(
        """
        SELECT id, event_type, email_id, event_at, extract_note
        FROM application_events
        ORDER BY event_at, email_id
        """,
    ).fetchall()
    rerun_result = service.run([extraction_1, extraction_2])

    rerun_application_ids = connection.execute(
        "SELECT id FROM applications ORDER BY id",
    ).fetchall()
    rerun_events = connection.execute(
        """
        SELECT id, event_type, email_id, event_at, extract_note
        FROM application_events
        ORDER BY event_at, email_id
        """,
    ).fetchall()

    assert rerun_result.extraction_count == 2
    assert len(rerun_application_ids) == 1
    assert rerun_application_ids == first_application_ids
    assert len(rerun_events) == 2
    assert rerun_events == first_events


def test_aggregation_starts_new_attempt_after_terminal_same_thread_application(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    for email_id in ("first-applied", "first-rejected", "second-applied", "second-interview"):
        insert_raw_email(connection, email_id, thread_id="reused-ats-thread")
    connection.commit()

    first_applied = make_extraction(
        email_id="first-applied",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=datetime(2025, 1, 2, 10, 0, tzinfo=UTC),
    )
    first_rejected = make_extraction(
        email_id="first-rejected",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.REJECTION,
        status="rejected",
        event_type="rejection",
        event_at=datetime(2025, 1, 10, 10, 0, tzinfo=UTC),
    )
    second_applied = make_extraction(
        email_id="second-applied",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )
    second_interview = make_extraction(
        email_id="second-interview",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.INTERVIEW_INVITE,
        status="interview",
        event_type="interview_scheduled",
        event_at=datetime(2026, 1, 12, 10, 0, tzinfo=UTC),
    )
    service = make_service(connection)

    service.run([first_applied, first_rejected])
    service.run([second_applied])
    service.run([second_interview])
    first_snapshot = connection.execute(
        """
        SELECT applications.id, applications.current_status,
               GROUP_CONCAT(application_events.email_id, ',')
        FROM applications
        JOIN application_events ON application_events.application_id = applications.id
        GROUP BY applications.id
        ORDER BY applications.first_seen_at
        """,
    ).fetchall()

    service.run([first_applied, first_rejected, second_applied, second_interview])
    rerun_snapshot = connection.execute(
        """
        SELECT applications.id, applications.current_status,
               GROUP_CONCAT(application_events.email_id, ',')
        FROM applications
        JOIN application_events ON application_events.application_id = applications.id
        GROUP BY applications.id
        ORDER BY applications.first_seen_at
        """,
    ).fetchall()

    assert [tuple(row) for row in first_snapshot] == [
        (first_snapshot[0][0], "rejected", "first-applied,first-rejected"),
        (first_snapshot[1][0], "interview", "second-applied,second-interview"),
    ]
    assert MetricsRepository(connection).count_total_applications() == 2
    assert rerun_snapshot == first_snapshot


def test_aggregation_starts_new_attempt_after_terminal_application_without_thread(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    for email_id in ("first-applied", "first-rejected", "second-applied", "second-interview"):
        insert_raw_email(connection, email_id, thread_id=None)
    connection.commit()

    first_applied = make_extraction(
        email_id="first-applied",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
    )
    first_rejected = make_extraction(
        email_id="first-rejected",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.REJECTION,
        status="rejected",
        event_type="rejection",
        event_at=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
    second_applied = make_extraction(
        email_id="second-applied",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=datetime(2026, 1, 2, 11, 0, tzinfo=UTC),
    )
    second_interview = make_extraction(
        email_id="second-interview",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.INTERVIEW_INVITE,
        status="interview",
        event_type="interview_scheduled",
        event_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
    )
    service = make_service(connection)

    service.run([first_applied, first_rejected])
    service.run([second_applied])
    service.run([second_interview])
    first_snapshot = connection.execute(
        """
        SELECT applications.id, applications.current_status,
               GROUP_CONCAT(application_events.email_id, ',')
        FROM applications
        JOIN application_events ON application_events.application_id = applications.id
        GROUP BY applications.id
        ORDER BY applications.first_seen_at
        """
    ).fetchall()

    service.run([first_applied, first_rejected, second_applied, second_interview])
    rerun_snapshot = connection.execute(
        """
        SELECT applications.id, applications.current_status,
               GROUP_CONCAT(application_events.email_id, ',')
        FROM applications
        JOIN application_events ON application_events.application_id = applications.id
        GROUP BY applications.id
        ORDER BY applications.first_seen_at
        """
    ).fetchall()

    assert [tuple(row) for row in first_snapshot] == [
        (first_snapshot[0][0], "rejected", "first-applied,first-rejected"),
        (first_snapshot[1][0], "interview", "second-applied,second-interview"),
    ]
    assert MetricsRepository(connection).count_total_applications() == 2
    assert rerun_snapshot == first_snapshot


def test_aggregation_replayed_incremental_batch_does_not_duplicate_existing_event(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    extraction_1 = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    extraction_2 = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Software Engineer",
        category=JobEmailCategory.INTERVIEW_INVITE,
        status="interview",
        event_type="interview_scheduled",
        event_at=datetime(2026, 7, 8, 10, 0, tzinfo=UTC),
    )
    service = make_service(connection)

    service.run([extraction_1])
    service.run([extraction_1, extraction_2])
    event_rows_after_incremental = connection.execute(
        """
        SELECT id, event_type, email_id, event_at
        FROM application_events
        ORDER BY event_at, email_id
        """,
    ).fetchall()
    service.run([extraction_1, extraction_2])

    application_count = connection.execute("SELECT COUNT(*) FROM applications").fetchone()
    event_rows_after_replay = connection.execute(
        """
        SELECT id, event_type, email_id, event_at
        FROM application_events
        ORDER BY event_at, email_id
        """,
    ).fetchall()

    assert application_count is not None
    assert application_count[0] == 1
    assert len(event_rows_after_replay) == 2
    assert event_rows_after_replay == event_rows_after_incremental
    assert_current_status(connection, "interview")


def test_aggregation_uses_email_sent_at_for_missing_event_at_idempotency(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=None,
    )
    service = make_service(connection)

    service.run([extraction])
    service.run([extraction])

    stored_events = connection.execute(
        "SELECT event_at FROM application_events",
    ).fetchall()

    assert len(stored_events) == 1
    assert stored_events[0][0] == NOW.isoformat()


def test_aggregation_skips_non_job_related_extractions(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-def")
    connection.commit()

    job_extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
        is_job_related=True,
    )
    non_job_extraction = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
        is_job_related=False,
    )
    service = make_service(connection)
    result = service.run([job_extraction, non_job_extraction])

    assert result.extraction_count == 2
    assert result.applications_upserted == 1
    assert result.events_upserted == 1
    assert result.skipped_not_job_related == 1

    stored_apps = connection.execute("SELECT COUNT(*) FROM applications").fetchone()
    assert stored_apps is not None
    assert stored_apps[0] == 1


def test_aggregation_handles_different_grouping_keys_separately(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-xyz")
    connection.commit()

    extraction_1 = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    extraction_2 = make_extraction(
        email_id="email-2",
        company="Beta Inc",
        role_title="Data Scientist",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    service = make_service(connection)
    result = service.run([extraction_1, extraction_2])

    assert result.applications_upserted == 2
    assert result.events_upserted == 2

    stored_apps = connection.execute(
        "SELECT company FROM applications ORDER BY company",
    ).fetchall()
    assert len(stored_apps) == 2
    assert tuple(stored_apps[0]) == ("Acme Corp",)
    assert tuple(stored_apps[1]) == ("Beta Inc",)


def test_aggregation_updates_existing_application_when_new_extractions_arrive(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    extraction_1 = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    extraction_2 = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Software Engineer",
        status="rejected",
        event_type="rejection",
        event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
    )
    service = make_service(connection)

    result_1 = service.run([extraction_1])
    assert result_1.applications_upserted == 1
    assert result_1.events_upserted == 1

    current_status_before = connection.execute(
        "SELECT current_status FROM applications",
    ).fetchone()
    assert current_status_before is not None
    assert current_status_before[0] == "applied"

    result_2 = service.run([extraction_1, extraction_2])
    assert result_2.applications_upserted == 1
    assert result_2.events_upserted == 2

    current_status_after = connection.execute(
        "SELECT current_status FROM applications",
    ).fetchone()
    assert current_status_after is not None
    assert current_status_after[0] == "rejected"

    stored_events = connection.execute(
        "SELECT COUNT(*) FROM application_events",
    ).fetchone()
    assert stored_events is not None
    assert stored_events[0] == 2


def test_aggregation_reports_manual_lock_conflict_without_overwriting_application(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    changed_extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="offer",
        event_type="offer",
        event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
    )
    service = make_service(connection)

    service.run([extraction])
    stored_id = connection.execute("SELECT id FROM applications").fetchone()
    assert stored_id is not None
    connection.execute(
        """
        UPDATE applications
        SET manual_lock = 1, current_status = 'rejected'
        """,
    )
    connection.commit()

    result = service.run([changed_extraction])
    rerun_result = service.run([changed_extraction])

    assert result.applications_upserted == 0
    assert result.events_upserted == 0
    assert result.manual_conflict_count == 1
    assert result.manual_conflict_application_ids == [stored_id[0]]
    assert result.merged_source_skip_count == 0
    assert rerun_result.manual_conflict_count == 1
    stored_app = connection.execute(
        "SELECT company, role_title, current_status FROM applications",
    ).fetchone()
    assert stored_app is not None
    assert tuple(stored_app) == ("Acme Corp", "Software Engineer", "rejected")
    conflict_rows = connection.execute(
        """
        SELECT conflict_key, conflict_type, evidence_email_id, existing_json, proposed_json
        FROM application_correction_conflicts
        """,
    ).fetchall()
    assert len(conflict_rows) == 1
    conflict_key, conflict_type, evidence_email_id, existing_json, proposed_json = tuple(
        conflict_rows[0]
    )
    assert conflict_key == f"application_summary:{stored_id[0]}:email-1"
    assert conflict_type == "application_summary"
    assert evidence_email_id == "email-1"
    existing = json.loads(existing_json)
    proposed = json.loads(proposed_json)
    assert existing["application"]["current_status"] == "rejected"
    assert proposed["application"]["current_status"] == "offer"
    assert proposed["evidence_email_ids"] == ["email-1"]


def test_aggregation_does_not_report_conflict_for_unchanged_locked_rerun(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    service = make_service(connection)

    service.run([extraction])
    connection.execute("UPDATE applications SET manual_lock = 1")
    connection.commit()

    result = service.run([extraction])

    assert result.applications_upserted == 0
    assert result.events_upserted == 1
    assert result.manual_conflict_count == 0
    assert result.manual_conflict_application_ids == []
    assert result.merged_source_skip_count == 0
    stored_events = connection.execute(
        "SELECT COUNT(*) FROM application_events",
    ).fetchone()
    assert stored_events is not None
    assert stored_events[0] == 1


def test_aggregation_reports_conflict_instead_of_overwriting_manual_event_edit(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    connection.commit()

    extraction = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
    )
    service = make_service(connection)
    service.run([extraction])

    stored_event = connection.execute(
        "SELECT id, application_id FROM application_events",
    ).fetchone()
    assert stored_event is not None
    event_id = stored_event[0]
    application_id = stored_event[1]
    edited_at = datetime(2026, 7, 8, 10, 0, tzinfo=UTC)
    connection.execute(
        """
        UPDATE application_events
        SET event_type = 'interview_scheduled',
            event_at = ?,
            extract_note = 'Manual timeline correction.'
        WHERE id = ?
        """,
        (edited_at.isoformat(), event_id),
    )
    connection.execute(
        """
        UPDATE applications
        SET current_status = 'interview',
            last_activity_at = ?,
            manual_lock = 1
        WHERE id = ?
        """,
        (edited_at.isoformat(), application_id),
    )
    connection.execute(
        """
        INSERT INTO application_corrections (
            application_id, correction_type, before_json,
            after_json, reason, created_at
        ) VALUES (?, 'event_edit', ?, ?, ?, ?)
        """,
        (
            application_id,
            json.dumps({"event": {"id": event_id, "event_type": "applied"}}),
            json.dumps(
                {
                    "event": {
                        "id": event_id,
                        "event_type": "interview_scheduled",
                    }
                }
            ),
            "Manual event correction.",
            NOW.isoformat(),
        ),
    )
    connection.commit()

    result = service.run([extraction])

    assert result.events_upserted == 0
    assert result.manual_conflict_count == 1
    assert result.manual_conflict_application_ids == [application_id]
    event_after_rerun = connection.execute(
        "SELECT event_type, event_at, extract_note FROM application_events WHERE id = ?",
        (event_id,),
    ).fetchone()
    assert event_after_rerun is not None
    assert tuple(event_after_rerun) == (
        "interview_scheduled",
        edited_at.isoformat(),
        "Manual timeline correction.",
    )
    conflict_row = connection.execute(
        """
        SELECT conflict_key, conflict_type, evidence_email_id, existing_json, proposed_json
        FROM application_correction_conflicts
        """,
    ).fetchone()
    assert conflict_row is not None
    conflict_key, conflict_type, evidence_email_id, existing_json, proposed_json = tuple(
        conflict_row
    )
    assert conflict_key == f"application_event:{application_id}:email-1"
    assert conflict_type == "application_event"
    assert evidence_email_id == "email-1"
    existing = json.loads(existing_json)
    proposed = json.loads(proposed_json)
    assert existing["event"]["event_type"] == "interview_scheduled"
    assert proposed["event"]["event_type"] == "applied"


def test_aggregation_merges_tech_stack_from_multiple_extractions(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    insert_raw_email(connection, "email-1", thread_id="thread-abc")
    insert_raw_email(connection, "email-2", thread_id="thread-abc")
    connection.commit()

    extraction_1 = make_extraction(
        email_id="email-1",
        company="Acme Corp",
        role_title="Software Engineer",
        status="applied",
        event_type="applied",
        event_at=EVENT_AT,
        tech_stack=["Python", "FastAPI"],
    )
    extraction_2 = make_extraction(
        email_id="email-2",
        company="Acme Corp",
        role_title="Software Engineer",
        status="rejected",
        event_type="rejection",
        event_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        tech_stack=["Python", "Django", "AWS"],
    )
    service = make_service(connection)
    result = service.run([extraction_1, extraction_2])

    assert result.applications_upserted == 1
    assert result.events_upserted == 2

    tech_stack = connection.execute(
        "SELECT tech_stack FROM applications",
    ).fetchone()
    assert tech_stack is not None
    tech_list = tech_stack[0]
    assert "Python" in tech_list
    assert "FastAPI" in tech_list
    assert "Django" in tech_list
    assert "AWS" in tech_list


def test_empty_accepted_extractions_returns_zero_counts(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    service = make_service(connection)
    result = service.run([])

    assert result.extraction_count == 0
    assert result.applications_upserted == 0
    assert result.events_upserted == 0
    assert result.skipped_not_job_related == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(str(database_path))


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    thread_id: str | None = None,
    body_text: str | None = "Test body content.",
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
            thread_id,
            "jobs@example.test",
            "me@example.test",
            "Job update",
            sent_at.isoformat(),
            body_text,
            "retained" if body_text is not None else "metadata_only",
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def assert_current_status(
    connection: sqlite3.Connection,
    expected: ApplicationStatus,
) -> None:
    current_status = connection.execute(
        "SELECT current_status FROM applications",
    ).fetchone()
    assert current_status is not None
    assert current_status[0] == expected


def make_extraction(
    *,
    email_id: str = "email-1",
    is_job_related: bool = True,
    company: str | None = None,
    role_title: str | None = None,
    category: JobEmailCategory = JobEmailCategory.APPLICATION_CONFIRMATION,
    confidence: float = 0.95,
    classified_at: datetime = NOW,
    status: ApplicationStatus | None = "applied",
    event_type: ApplicationEventType | None = "applied",
    event_at: datetime | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    currency: str | None = None,
    location: str | None = None,
    work_mode: WorkMode | None = None,
    seniority: str | None = None,
    sponsorship: SponsorshipStatus = "unknown",
    tech_stack: list[str] | None = None,
    rejection_reason: str | None = None,
) -> AcceptedLLMExtraction:
    return AcceptedLLMExtraction(
        classification=EmailClassificationRecord(
            email_id=email_id,
            is_job_related=is_job_related,
            category=category,
            confidence=confidence,
            model="test-model",
            prompt_version="v1",
            classified_at=classified_at,
        ),
        extraction=JobApplicationExtraction(
            company=company,
            role_title=role_title,
            status=status,
            event_type=event_type,
            event_at=event_at,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            location=location,
            work_mode=work_mode,
            seniority=seniority,
            sponsorship=sponsorship,
            tech_stack=tech_stack or [],
            rejection_reason=rejection_reason,
        ),
    )


def make_service(connection: sqlite3.Connection) -> AggregationService:
    return AggregationService(
        application_repository=ApplicationRepository(connection),
        event_repository=EventRepository(connection),
        email_repository=EmailRepository(connection),
        correction_conflict_repository=CorrectionConflictRepository(connection),
        clock=lambda: NOW,
        run_id_factory=lambda: "test-run",
    )
