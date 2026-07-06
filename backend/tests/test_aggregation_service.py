from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import ApplicationRepository, EmailRepository, EventRepository
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
            NOW.isoformat(),
            body_text,
            "retained" if body_text is not None else "metadata_only",
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def make_extraction(
    *,
    email_id: str = "email-1",
    is_job_related: bool = True,
    company: str | None = None,
    role_title: str | None = None,
    category: JobEmailCategory = JobEmailCategory.APPLICATION_CONFIRMATION,
    confidence: float = 0.95,
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
            classified_at=NOW,
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
        clock=lambda: NOW,
        run_id_factory=lambda: "test-run",
    )
