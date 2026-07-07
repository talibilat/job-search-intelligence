from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.db.repositories import ApplicationRepository, SyntheticFixtureRepository
from app.services.metrics import MetricsService

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def test_metrics_service_returns_foundational_counts_from_applications() -> None:
    connection = sqlite3.connect(":memory:")
    SyntheticFixtureRepository(connection).load_file(sample_fixture_path())
    insert_application(connection)

    snapshot = MetricsService(
        ApplicationRepository(connection),
        clock=lambda: NOW,
    ).get_foundational_metrics()

    assert snapshot.total_applications == 2
    assert snapshot.distinct_companies == 2
    assert [(item.status, item.count) for item in snapshot.status_counts] == [
        ("applied", 0),
        ("in_review", 0),
        ("assessment", 0),
        ("interview", 1),
        ("offer", 0),
        ("rejected", 1),
        ("ghosted", 0),
        ("withdrawn", 0),
    ]
    assert snapshot.generated_at == NOW


def test_metrics_service_returns_zero_counts_without_applications() -> None:
    connection = sqlite3.connect(":memory:")
    SyntheticFixtureRepository(connection).load_file(sample_fixture_path())
    connection.execute("DELETE FROM application_events")
    connection.execute("DELETE FROM applications")

    snapshot = MetricsService(
        ApplicationRepository(connection),
        clock=lambda: NOW,
    ).get_foundational_metrics()

    assert snapshot.total_applications == 0
    assert snapshot.distinct_companies == 0
    assert all(item.count == 0 for item in snapshot.status_counts)


def sample_fixture_path() -> Path:
    backend_root = Path(__file__).resolve().parents[1]
    return backend_root / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"


def insert_application(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id,
            company,
            role_title,
            source,
            first_seen_at,
            current_status,
            salary_min,
            salary_max,
            currency,
            location,
            work_mode,
            seniority,
            sponsorship,
            tech_stack,
            last_activity_at,
            manual_lock,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "application-beta-frontend",
            "Beta Labs",
            "Frontend Engineer",
            "company_site",
            "2026-07-21T09:00:00+00:00",
            "interview",
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            "[]",
            "2026-07-22T10:00:00+00:00",
            0,
            "2026-07-21T09:01:00+00:00",
            "2026-07-22T10:01:00+00:00",
        ),
    )
