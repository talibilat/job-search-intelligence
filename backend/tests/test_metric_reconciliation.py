from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository, EventRepository, MetricsRepository
from app.main import create_app
from app.models import MetricRateRow
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class DisplayedRate(TypedDict):
    numerator: int
    denominator: int
    rate: float | None


def test_metrics_summary_reconciles_with_repository_queries(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_reconciliation_fixture(connection)
        repository = MetricsRepository(connection)
        ghost_cutoff_at = datetime.now(UTC) - timedelta(days=30)

        expected = {
            "total_applications": repository.count_total_applications(),
            "distinct_company_count": repository.count_distinct_companies(),
            "offers_received": repository.count_applications_with_offer_events(),
            "ghosted_applications": repository.count_threshold_ghosted_applications(
                cutoff_at=ghost_cutoff_at.isoformat(),
            ),
            "rejected_applications": repository.count_rejected_applications(),
            "interview_invitation_count": repository.count_interview_invitation_events(),
        }

    response = create_test_client(database_path).get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    for field, expected_value in expected.items():
        assert_reconciles(field=field, displayed_value=body[field], query_value=expected_value)


def test_metrics_rates_reconcile_with_repository_queries(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_reconciliation_fixture(connection)
        repository = MetricsRepository(connection)
        ghost_cutoff_at = datetime.now(UTC) - timedelta(days=30)
        expected_rates = {
            metric.name: metric
            for metric in repository.get_rate_metrics(ghost_cutoff_at=ghost_cutoff_at.isoformat())
        }

    response = create_test_client(database_path).get("/metrics/rates")

    assert response.status_code == 200
    body = response.json()
    assert_rate_reconciles(
        field="overall_response_rate",
        displayed=body["overall_response_rate"],
        query=expected_rates["response"],
    )
    assert_rate_reconciles(
        field="rejection_rate",
        displayed=body["rejection_rate"],
        query=expected_rates["rejection"],
    )
    assert_rate_reconciles(
        field="ghost_rate",
        displayed=body["ghost_rate"],
        query=expected_rates["ghost"],
    )
    assert_rate_reconciles(
        field="application_to_interview_rate",
        displayed=body["application_to_interview_rate"],
        query=expected_rates["application_to_interview"],
    )


def assert_reconciles(*, field: str, displayed_value: int, query_value: int) -> None:
    assert displayed_value == query_value, f"{field} did not reconcile with repository query"


def assert_rate_reconciles(
    *,
    field: str,
    displayed: DisplayedRate,
    query: MetricRateRow,
) -> None:
    assert_reconciles(
        field=f"{field}.numerator",
        displayed_value=displayed["numerator"],
        query_value=query.numerator,
    )
    assert_reconciles(
        field=f"{field}.denominator",
        displayed_value=displayed["denominator"],
        query_value=query.denominator,
    )
    assert displayed["rate"] == query.rate, (
        f"{field}.rate did not reconcile with repository query"
    )


def create_test_client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        ghost_threshold_days=30,
        sync_on_open=False,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def seed_reconciliation_fixture(connection: sqlite3.Connection) -> None:
    insert_application_with_events(
        connection,
        application_id="app-response",
        company="Acme Corp",
        current_status="in_review",
        event_types=("applied", "response"),
    )
    insert_application_with_events(
        connection,
        application_id="app-rejected",
        company="Acme Corp",
        current_status="rejected",
        event_types=("applied", "rejection"),
    )
    insert_application_with_events(
        connection,
        application_id="app-interview",
        company="Beta LLC",
        current_status="interview",
        event_types=("applied", "interview_scheduled"),
    )
    insert_application_with_events(
        connection,
        application_id="app-offer",
        company="Beta LLC",
        current_status="offer",
        event_types=("applied", "interview_scheduled", "offer"),
    )
    insert_application_with_events(
        connection,
        application_id="app-silent-old",
        company="Gamma Inc",
        current_status="applied",
        event_date_prefix="2020-01",
        event_types=("applied",),
    )


def insert_application_with_events(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str,
    current_status: str,
    event_types: tuple[str, ...],
    event_date_prefix: str = "2026-07",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=company,
        role_title="Software Engineer",
        source="linkedin",
        first_seen_at=f"{event_date_prefix}-01T09:00:00+00:00",
        current_status=current_status,
        last_activity_at=f"{event_date_prefix}-01T09:00:00+00:00",
        created_at=f"{event_date_prefix}-01T09:01:00+00:00",
        updated_at=f"{event_date_prefix}-01T09:01:00+00:00",
        sponsorship="unknown",
        tech_stack=[],
    )
    event_repository = EventRepository(connection)
    for index, event_type in enumerate(event_types):
        email_id = None if event_type == "ghost_inferred" else f"{application_id}-email-{index}"
        if email_id is not None:
            insert_raw_email(connection, email_id=email_id)
        event_repository.upsert_event(
            id=f"{application_id}-event-{index}",
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=f"{event_date_prefix}-{index + 1:02d}T09:00:00+00:00",
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
