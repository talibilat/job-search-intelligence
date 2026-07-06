from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.db.repositories import ApplicationRepository, EventRepository, InsightRepository
from app.services.insights_service import InsightInputBuilder

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_insight_input_builder_prepares_facts_citations_and_hash(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        insert_interview_application_fixture(connection)

        builder = InsightInputBuilder(InsightRepository(connection))
        insight_input = builder.build("why_rejected")
        repeated_input = builder.build("why_rejected")

    fact_values = {fact.name: fact.value for fact in insight_input.facts}
    assert insight_input.type == "why_rejected"
    assert fact_values["total_applications"] == 2
    assert fact_values["status_counts"] == {"interview": 1, "rejected": 1}
    assert fact_values["event_type_counts"] == {
        "applied": 2,
        "interview_scheduled": 1,
        "rejection": 1,
    }
    assert [evidence.event_id for evidence in insight_input.evidence] == [
        "event-rejected-rejection",
    ]
    rejection_evidence = insight_input.evidence[0]
    assert rejection_evidence.citation_id == (
        "application:application-rejected|event:event-rejected-rejection|email:email-rejection"
    )
    assert rejection_evidence.application_id == "application-rejected"
    assert rejection_evidence.email_id == "email-rejection"
    assert rejection_evidence.company == "Acme Corp"
    assert rejection_evidence.email_subject == "Update on your application"
    assert (
        rejection_evidence.email_body_text
        == "Unfortunately, we moved forward with candidates who had more Kubernetes experience."
    )
    assert "Unfortunately" not in repr(rejection_evidence)
    assert len(insight_input.inputs_hash) == 64
    assert insight_input.inputs_hash == repeated_input.inputs_hash


def test_insight_input_builder_hash_changes_when_source_evidence_changes(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        builder = InsightInputBuilder(InsightRepository(connection))

        original_hash = builder.build("why_rejected").inputs_hash
        connection.execute(
            "UPDATE application_events SET extract_note = ? WHERE id = ?",
            (
                "Rejection mentioned Kubernetes and distributed systems experience.",
                "event-rejected-rejection",
            ),
        )
        connection.commit()

        updated_hash = builder.build("why_rejected").inputs_hash

    assert updated_hash != original_hash


def test_insight_input_builder_hash_covers_limited_out_evidence(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        insert_second_rejected_application_fixture(connection)
        builder = InsightInputBuilder(InsightRepository(connection))

        original = builder.build("why_rejected", max_evidence_items=1)
        connection.execute(
            "UPDATE application_events SET extract_note = ? WHERE id = ?",
            (
                "Second rejection mentioned missing platform depth.",
                "event-second-rejection",
            ),
        )
        connection.commit()

        updated = builder.build("why_rejected", max_evidence_items=1)

    assert [evidence.event_id for evidence in original.evidence] == [
        "event-rejected-rejection",
    ]
    assert [evidence.event_id for evidence in updated.evidence] == [
        "event-rejected-rejection",
    ]
    assert updated.inputs_hash != original.inputs_hash


def test_insight_input_builder_keeps_debugging_bodies_out_of_evidence(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        insert_raw_email(
            connection,
            email_id="email-debug-feedback",
            subject="Detailed feedback",
            body_text="Private debugging copy of interview feedback.",
            sent_at="2026-07-05T10:00:00+00:00",
            body_retention_state="debugging",
        )
        EventRepository(connection).upsert_event(
            id="event-debug-feedback",
            application_id="application-rejected",
            email_id="email-debug-feedback",
            event_type="feedback",
            event_at="2026-07-05T10:00:00+00:00",
            extract_note="Debug feedback retained for reconciliation.",
        )
        connection.commit()

        insight_input = InsightInputBuilder(InsightRepository(connection)).build(
            "why_rejected",
        )

    debug_evidence = next(
        evidence
        for evidence in insight_input.evidence
        if evidence.event_id == "event-debug-feedback"
    )
    assert debug_evidence.email_subject == "Detailed feedback"
    assert debug_evidence.email_body_text is None
    assert "Private debugging" not in insight_input.model_dump_json()


def test_weekly_actions_input_prefers_open_current_evidence(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_rejected_application_fixture(connection)
        insert_interview_application_fixture(connection)

        insight_input = InsightInputBuilder(InsightRepository(connection)).build(
            "weekly_actions",
            max_evidence_items=1,
        )

    assert [evidence.application_id for evidence in insight_input.evidence] == [
        "application-interview",
    ]
    assert [evidence.event_id for evidence in insight_input.evidence] == [
        "event-interview-invite",
    ]


def test_insight_input_builder_rejects_empty_evidence_limit(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        builder = InsightInputBuilder(InsightRepository(connection))

        with pytest.raises(ValueError, match="max_evidence_items must be at least 1"):
            builder.build("story", max_evidence_items=0)


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def insert_rejected_application_fixture(connection: sqlite3.Connection) -> None:
    insert_raw_email(
        connection,
        email_id="email-applied",
        subject="Application received",
        body_text="Thanks for applying to Acme Corp.",
        sent_at="2026-07-01T09:00:00+00:00",
    )
    insert_raw_email(
        connection,
        email_id="email-rejection",
        subject="Update on your application",
        body_text=(
            "Unfortunately, we moved forward with candidates who had more Kubernetes experience."
        ),
        sent_at="2026-07-04T10:00:00+00:00",
    )
    insert_application(
        connection,
        application_id="application-rejected",
        current_status="rejected",
        last_activity_at="2026-07-04T10:00:00+00:00",
    )
    event_repository = EventRepository(connection)
    event_repository.upsert_event(
        id="event-rejected-applied",
        application_id="application-rejected",
        email_id="email-applied",
        event_type="applied",
        event_at="2026-07-01T09:00:00+00:00",
        extract_note="Application confirmation received.",
    )
    event_repository.upsert_event(
        id="event-rejected-rejection",
        application_id="application-rejected",
        email_id="email-rejection",
        event_type="rejection",
        event_at="2026-07-04T10:00:00+00:00",
        extract_note="Rejection mentioned Kubernetes experience.",
    )
    connection.commit()


def insert_interview_application_fixture(connection: sqlite3.Connection) -> None:
    insert_raw_email(
        connection,
        email_id="email-interview-applied",
        subject="Thanks for applying",
        body_text="Thanks for applying to Beta LLC.",
        sent_at="2026-07-02T09:00:00+00:00",
    )
    insert_raw_email(
        connection,
        email_id="email-interview",
        subject="Interview invitation",
        body_text="We would like to invite you to interview with Beta LLC.",
        sent_at="2026-07-05T10:00:00+00:00",
    )
    insert_application(
        connection,
        application_id="application-interview",
        company="Beta LLC",
        current_status="interview",
        first_seen_at="2026-07-02T09:00:00+00:00",
        last_activity_at="2026-07-05T10:00:00+00:00",
    )
    event_repository = EventRepository(connection)
    event_repository.upsert_event(
        id="event-interview-applied",
        application_id="application-interview",
        email_id="email-interview-applied",
        event_type="applied",
        event_at="2026-07-02T09:00:00+00:00",
        extract_note="Application confirmation received.",
    )
    event_repository.upsert_event(
        id="event-interview-invite",
        application_id="application-interview",
        email_id="email-interview",
        event_type="interview_scheduled",
        event_at="2026-07-05T10:00:00+00:00",
        extract_note="Interview invite received.",
    )
    connection.commit()


def insert_second_rejected_application_fixture(connection: sqlite3.Connection) -> None:
    insert_raw_email(
        connection,
        email_id="email-second-rejection",
        subject="Your application status",
        body_text="We selected candidates with deeper platform engineering experience.",
        sent_at="2026-07-06T10:00:00+00:00",
    )
    insert_application(
        connection,
        application_id="application-second-rejected",
        company="Delta Inc",
        current_status="rejected",
        first_seen_at="2026-07-03T09:00:00+00:00",
        last_activity_at="2026-07-06T10:00:00+00:00",
    )
    EventRepository(connection).upsert_event(
        id="event-second-rejection",
        application_id="application-second-rejected",
        email_id="email-second-rejection",
        event_type="rejection",
        event_at="2026-07-06T10:00:00+00:00",
        extract_note="Second rejection mentioned platform engineering experience.",
    )
    connection.commit()


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str = "Acme Corp",
    role_title: str = "Backend Engineer",
    current_status: str = "rejected",
    first_seen_at: str = "2026-07-01T09:00:00+00:00",
    last_activity_at: str = "2026-07-04T10:00:00+00:00",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=company,
        role_title=role_title,
        source="linkedin",
        first_seen_at=first_seen_at,
        current_status=current_status,
        last_activity_at=last_activity_at,
        created_at=first_seen_at,
        updated_at=last_activity_at,
        salary_min=None,
        salary_max=None,
        currency=None,
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=["Python", "Kubernetes"],
    )
    connection.commit()


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    subject: str,
    body_text: str,
    sent_at: str,
    body_retention_state: str = "retained",
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            "thread-42",
            "jobs@example.test",
            "applicant@example.test",
            subject,
            sent_at,
            body_text,
            body_retention_state,
            "[]",
            "gmail",
            sent_at,
        ),
    )
    connection.commit()
