from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import (
    ApplicationRepository,
    EmailRepository,
    EventRepository,
    MetricsRepository,
)
from app.main import create_app
from app.models import (
    MetricRate,
    MetricRateRow,
    MetricsRatesResponse,
    MetricsSummaryResponse,
    RawEmailBodyRetentionState,
    RawEmailRecord,
)
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

        query_values = {
            "total_applications": repository.count_total_applications(),
            "distinct_company_count": repository.count_distinct_companies(),
            "offers_received": repository.count_applications_with_offer_events(),
            "ghosted_applications": repository.count_threshold_ghosted_applications(
                cutoff_at=ghost_cutoff_at.isoformat(),
            ),
            "rejected_applications": repository.count_rejected_applications(),
            "interview_invitation_count": repository.count_interview_invitation_events(),
        }
        query_window_counts = {
            "week": repository.count_applications_between(
                start_at="2026-07-13T00:00:00+00:00",
                end_at="2026-07-20T00:00:00+00:00",
            ),
            "month": repository.count_applications_between(
                start_at="2026-07-01T00:00:00+00:00",
                end_at="2026-08-01T00:00:00+00:00",
            ),
            "year": repository.count_applications_between(
                start_at="2026-01-01T00:00:00+00:00",
                end_at="2027-01-01T00:00:00+00:00",
            ),
        }

    manual_values = {
        "total_applications": 5,
        "distinct_company_count": 3,
        "offers_received": 1,
        "ghosted_applications": 1,
        "rejected_applications": 1,
        "interview_invitation_count": 2,
    }
    manual_window_counts = {"week": 0, "month": 4, "year": 4}

    response = create_test_client(database_path).get(
        "/metrics/summary?anchor_at=2026-07-15T12:00:00Z",
    )

    assert response.status_code == 200
    body = MetricsSummaryResponse.model_validate(response.json())
    for field, manual_value in manual_values.items():
        displayed_value = getattr(body, field)
        assert_reconciles(
            field=field,
            displayed_value=displayed_value,
            query_value=query_values[field],
        )
        assert_reconciles(field=field, displayed_value=displayed_value, query_value=manual_value)

    displayed_window_counts = {
        window.window.value: window.application_count for window in body.application_windows
    }
    for window, manual_count in manual_window_counts.items():
        assert_reconciles(
            field=f"application_windows.{window}",
            displayed_value=displayed_window_counts[window],
            query_value=query_window_counts[window],
        )
        assert_reconciles(
            field=f"application_windows.{window}",
            displayed_value=displayed_window_counts[window],
            query_value=manual_count,
        )


def test_metrics_rates_reconcile_with_repository_queries(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        seed_reconciliation_fixture(connection)
        repository = MetricsRepository(connection)
        ghost_cutoff_at = datetime.now(UTC) - timedelta(days=30)
        expected_rates = {
            metric.name: rate_payload(metric)
            for metric in repository.get_rate_metrics(ghost_cutoff_at=ghost_cutoff_at.isoformat())
        }
    manual_rates: dict[str, DisplayedRate] = {
        "overall_response_rate": {"numerator": 4, "denominator": 5, "rate": 0.8},
        "rejection_rate": {"numerator": 1, "denominator": 5, "rate": 0.2},
        "ghost_rate": {"numerator": 1, "denominator": 5, "rate": 0.2},
        "application_to_interview_rate": {"numerator": 2, "denominator": 5, "rate": 0.4},
        "interview_to_offer_rate": {"numerator": 1, "denominator": 2, "rate": 0.5},
    }

    response = create_test_client(database_path).get("/metrics/rates")

    assert response.status_code == 200
    body = MetricsRatesResponse.model_validate(response.json())
    assert_rate_reconciles(
        field="overall_response_rate",
        displayed=rate_payload(body.overall_response_rate),
        query=expected_rates["response"],
        manual=manual_rates["overall_response_rate"],
    )
    assert_rate_reconciles(
        field="rejection_rate",
        displayed=rate_payload(body.rejection_rate),
        query=expected_rates["rejection"],
        manual=manual_rates["rejection_rate"],
    )
    assert_rate_reconciles(
        field="ghost_rate",
        displayed=rate_payload(body.ghost_rate),
        query=expected_rates["ghost"],
        manual=manual_rates["ghost_rate"],
    )
    assert_rate_reconciles(
        field="application_to_interview_rate",
        displayed=rate_payload(body.application_to_interview_rate),
        query=expected_rates["application_to_interview"],
        manual=manual_rates["application_to_interview_rate"],
    )
    assert_rate_reconciles(
        field="interview_to_offer_rate",
        displayed=rate_payload(body.interview_to_offer_rate),
        query=expected_rates["interview_to_offer"],
        manual=manual_rates["interview_to_offer_rate"],
    )


def assert_reconciles(*, field: str, displayed_value: int, query_value: int) -> None:
    assert displayed_value == query_value, f"{field} did not reconcile with repository query"


def assert_rate_reconciles(
    *,
    field: str,
    displayed: DisplayedRate,
    query: DisplayedRate,
    manual: DisplayedRate,
) -> None:
    assert_reconciles(
        field=f"{field}.numerator",
        displayed_value=displayed["numerator"],
        query_value=query["numerator"],
    )
    assert_reconciles(
        field=f"{field}.numerator",
        displayed_value=displayed["numerator"],
        query_value=manual["numerator"],
    )
    assert_reconciles(
        field=f"{field}.denominator",
        displayed_value=displayed["denominator"],
        query_value=query["denominator"],
    )
    assert_reconciles(
        field=f"{field}.denominator",
        displayed_value=displayed["denominator"],
        query_value=manual["denominator"],
    )
    assert displayed["rate"] == query["rate"], (
        f"{field}.rate did not reconcile with repository query"
    )
    assert displayed["rate"] == manual["rate"], f"{field}.rate did not match manual count"


def rate_payload(metric: MetricRate | MetricRateRow) -> DisplayedRate:
    return {
        "numerator": metric.numerator,
        "denominator": metric.denominator,
        "rate": metric.rate,
    }


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
    EmailRepository(connection).upsert_raw_emails(
        (
            RawEmailRecord(
                id=email_id,
                thread_id=f"thread-{email_id}",
                from_addr="jobs@example.test",
                to_addr="applicant@example.test",
                subject="Application update",
                sent_at=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
                body_text="Synthetic retained body.",
                body_retention_state=RawEmailBodyRetentionState.RETAINED,
                labels=[],
                provider="gmail",
                ingested_at=datetime(2026, 7, 1, 9, 1, tzinfo=UTC),
            ),
        ),
    )
