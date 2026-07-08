from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import (
    ApplicationRepository,
    EventRepository,
    MetricsRepository,
    SyntheticFixtureRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_FIXTURE_PATH = BACKEND_ROOT / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"


def test_metrics_repository_matches_basic_synthetic_fixture() -> None:
    with sqlite3.connect(":memory:") as connection:
        SyntheticFixtureRepository(connection).load_file(SYNTHETIC_FIXTURE_PATH)
        repository = MetricsRepository(connection)

        total_applications = repository.count_total_applications()
        rejected_applications = repository.count_rejected_applications()
        rates = {
            metric.name: metric
            for metric in repository.get_rate_metrics(ghost_cutoff_at="2026-08-01T00:00:00+00:00")
        }
        funnel = {stage.stage: stage.count for stage in repository.get_funnel_metrics()}
        timeseries = repository.get_application_timeseries()
        source_rows = repository.get_breakdown("source")
        tech_rows = repository.get_breakdown("tech")

    assert total_applications == 1
    assert rejected_applications == 1
    assert rates["response"].numerator == 1
    assert rates["response"].denominator == 1
    assert rates["response"].rate == 1.0
    assert rates["rejection"].rate == 1.0
    assert rates["ghost"].rate == 0.0
    assert rates["application_to_interview"].rate == 0.0
    assert rates["interview_to_offer"].rate is None
    assert funnel == {
        "applied": 1,
        "response": 1,
        "assessment": 0,
        "interview": 0,
        "offer": 0,
    }
    assert [(point.period_start, point.application_count) for point in timeseries] == [
        ("2026-07-04", 1),
    ]
    assert [(row.value, row.application_count, row.response_count) for row in source_rows] == [
        ("company_site", 1, 1),
    ]
    assert [(row.value, row.application_count, row.response_count) for row in tech_rows] == [
        ("fastapi", 1, 1),
        ("python", 1, 1),
    ]


def test_metrics_repository_returns_counts_rates_and_funnel(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_metric_fixture(connection)
        repository = MetricsRepository(connection)

        total_applications = repository.count_total_applications()
        rates = {
            metric.name: metric
            for metric in repository.get_rate_metrics(ghost_cutoff_at="2026-07-02T09:00:00+00:00")
        }
        funnel = {stage.stage: stage.count for stage in repository.get_funnel_metrics()}

    assert total_applications == 5
    assert rates["response"].numerator == 3
    assert rates["response"].denominator == 5
    assert rates["response"].rate == 0.6
    assert rates["rejection"].rate == 0.2
    assert rates["ghost"].rate == 0.4
    assert rates["application_to_interview"].rate == 0.2
    assert rates["interview_to_offer"].rate == 1.0
    assert funnel == {
        "applied": 5,
        "response": 3,
        "assessment": 1,
        "interview": 1,
        "offer": 1,
    }


def test_funnel_metrics_count_offers_only_after_interviews(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-offer-without-interview",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="offer",
            tech_stack=["Python"],
            event_types=("applied", "offer"),
        )
        insert_application(
            connection,
            application_id="app-offer-before-interview",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="interview",
            tech_stack=["Python"],
            event_types=("applied", "offer", "interview_scheduled"),
        )

        funnel = {
            stage.stage: stage.count for stage in MetricsRepository(connection).get_funnel_metrics()
        }

    assert funnel["applied"] == 2
    assert funnel["response"] == 2
    assert funnel["interview"] == 1
    assert funnel["offer"] == 0


def test_rate_metrics_uses_threshold_ghost_count(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-silent-over-threshold",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="applied",
            tech_stack=["Python"],
            event_types=("applied",),
        )
        insert_application(
            connection,
            application_id="app-silent-under-threshold",
            source="linkedin",
            first_seen_at="2026-07-03T09:00:00+00:00",
            current_status="applied",
            tech_stack=["Python"],
            event_types=("applied",),
        )
        connection.execute(
            """
            UPDATE application_events
            SET event_at = ?
            WHERE application_id = ?
            """,
            ("2026-07-03T09:00:00+00:00", "app-silent-under-threshold"),
        )

        rates = {
            metric.name: metric
            for metric in MetricsRepository(connection).get_rate_metrics(
                ghost_cutoff_at="2026-07-02T09:00:00+00:00"
            )
        }

    assert rates["ghost"].numerator == 1
    assert rates["ghost"].denominator == 2
    assert rates["ghost"].rate == 0.5


def test_interview_to_offer_rate_counts_offers_only_after_interviews(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-offer-without-interview",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="offer",
            tech_stack=["Python"],
            event_types=("applied", "offer"),
        )

        rates = {
            metric.name: metric
            for metric in MetricsRepository(connection).get_rate_metrics(
                ghost_cutoff_at="2026-07-02T09:00:00+00:00"
            )
        }

    assert rates["interview_to_offer"].numerator == 0
    assert rates["interview_to_offer"].denominator == 0
    assert rates["interview_to_offer"].rate is None


def test_interview_to_offer_rate_excludes_offers_before_interviews(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-offer-before-interview",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="interview",
            tech_stack=["Python"],
            event_types=("applied", "offer", "interview_scheduled"),
        )

        rates = {
            metric.name: metric
            for metric in MetricsRepository(connection).get_rate_metrics(
                ghost_cutoff_at="2026-07-02T09:00:00+00:00"
            )
        }

    assert rates["interview_to_offer"].numerator == 0
    assert rates["interview_to_offer"].denominator == 1
    assert rates["interview_to_offer"].rate == 0.0


def test_interview_to_offer_rate_uses_event_id_tiebreaker(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-interview-offer-same-time",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="offer",
            tech_stack=["Python"],
            event_types=("applied", "interview_scheduled", "offer"),
        )
        connection.execute(
            """
            UPDATE application_events
            SET event_at = ?
            WHERE application_id = ?
              AND event_type IN ('interview_scheduled', 'offer')
            """,
            ("2026-07-02T09:00:00+00:00", "app-interview-offer-same-time"),
        )

        rates = {
            metric.name: metric
            for metric in MetricsRepository(connection).get_rate_metrics(
                ghost_cutoff_at="2026-07-02T09:00:00+00:00"
            )
        }

    assert rates["interview_to_offer"].numerator == 1
    assert rates["interview_to_offer"].denominator == 1
    assert rates["interview_to_offer"].rate == 1.0


def test_metrics_repository_returns_application_timeseries(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_metric_fixture(connection)
        points = MetricsRepository(connection).get_application_timeseries()

    assert [(point.period_start, point.application_count) for point in points] == [
        ("2026-07-01", 3),
        ("2026-07-02", 2),
    ]


def test_metrics_repository_returns_breakdowns(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_metric_fixture(connection)
        repository = MetricsRepository(connection)

        source_rows = repository.get_breakdown("source")
        tech_rows = repository.get_breakdown("tech")

    assert [(row.value, row.application_count) for row in source_rows] == [
        ("company_site", 2),
        ("linkedin", 3),
    ]
    assert [(row.value, row.application_count) for row in tech_rows] == [
        ("fastapi", 2),
        ("python", 5),
        ("react", 1),
    ]
    linkedin = next(row for row in source_rows if row.value == "linkedin")
    assert linkedin.response_count == 1
    assert linkedin.interview_count == 1
    assert linkedin.offer_count == 1


def test_tech_breakdown_counts_event_metrics_once_per_application(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-duplicate-tech",
            source="linkedin",
            first_seen_at="2026-07-01T09:00:00+00:00",
            current_status="offer",
            tech_stack=["Python", " python ", "PYTHON"],
            event_types=("applied", "response", "interview_scheduled", "offer"),
        )
        connection.execute(
            "UPDATE applications SET tech_stack = ? WHERE id = ?",
            (json.dumps(["Python", " python ", "PYTHON"]), "app-duplicate-tech"),
        )

        tech_rows = MetricsRepository(connection).get_breakdown("tech")

    assert len(tech_rows) == 1
    python = tech_rows[0]
    assert python.value == "python"
    assert python.application_count == 1
    assert python.response_count == 1
    assert python.interview_count == 1
    assert python.offer_count == 1


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def seed_metric_fixture(connection: sqlite3.Connection) -> None:
    insert_application(
        connection,
        application_id="app-silent",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="applied",
        tech_stack=["Python"],
        event_types=("applied",),
    )
    insert_application(
        connection,
        application_id="app-rejected",
        source="company_site",
        first_seen_at="2026-07-01T10:00:00+00:00",
        current_status="rejected",
        tech_stack=["Python", "FastAPI"],
        event_types=("applied", "rejection"),
    )
    insert_application(
        connection,
        application_id="app-interview-offer",
        source="linkedin",
        first_seen_at="2026-07-01T11:00:00+00:00",
        current_status="offer",
        tech_stack=["Python", "FastAPI"],
        event_types=("applied", "response", "interview_scheduled", "offer"),
    )
    insert_application(
        connection,
        application_id="app-assessment",
        source="company_site",
        first_seen_at="2026-07-02T09:00:00+00:00",
        current_status="assessment",
        tech_stack=["Python"],
        event_types=("applied", "assessment"),
    )
    insert_application(
        connection,
        application_id="app-ghosted",
        source="linkedin",
        first_seen_at="2026-07-02T10:00:00+00:00",
        current_status="ghosted",
        tech_stack=["Python", "React"],
        event_types=("applied", "ghost_inferred"),
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    source: str,
    first_seen_at: str,
    current_status: str,
    tech_stack: list[str],
    event_types: tuple[str, ...],
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=f"{application_id} Inc",
        role_title="Software Engineer",
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
        last_activity_at="2026-07-05T09:00:00+00:00",
        created_at=first_seen_at,
        updated_at="2026-07-05T09:00:00+00:00",
        salary_min=120000,
        salary_max=150000,
        currency="USD",
        location="Remote",
        work_mode="remote",
        seniority="senior",
        sponsorship="unknown",
        tech_stack=tech_stack,
    )
    event_repository = EventRepository(connection)
    for index, event_type in enumerate(event_types, start=1):
        email_id = None if event_type == "ghost_inferred" else f"{application_id}-email-{index}"
        if email_id is not None:
            insert_raw_email(connection, email_id=email_id)
        event_repository.upsert_event(
            id=f"{application_id}-event-{index}",
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=f"2026-07-0{index}T09:00:00+00:00",
        )
    connection.commit()


def insert_raw_email(connection: sqlite3.Connection, *, email_id: str) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "applicant@example.test",
            "Application update",
            "2026-07-01T09:00:00+00:00",
            "Synthetic retained body.",
            "retained",
            "[]",
            "gmail",
            "2026-07-01T09:01:00+00:00",
        ),
    )
