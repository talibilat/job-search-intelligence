from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from app.agent.tools.structured_query import (
    DateWindowSpec,
    StructuredQueryRequest,
    StructuredQueryTool,
)
from app.db.repositories import MetricsRepository, SyntheticFixtureRepository
from app.models.metrics import MetricsFilter

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FIXTURE = BACKEND_ROOT / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"


def test_last_week_resolves_across_year_boundary() -> None:
    with empty_connection() as connection:
        result = tool(connection, datetime(2026, 1, 7, 12, tzinfo=UTC)).run(
            StructuredQueryRequest(
                template="application_list",
                date_window=DateWindowSpec(kind="last_week"),
                timezone="UTC",
            )
        )

    assert result.resolved_date_window is not None
    assert result.resolved_date_window.start_at.isoformat() == "2025-12-29T00:00:00+00:00"
    assert result.resolved_date_window.end_at.isoformat() == "2026-01-05T00:00:00+00:00"


def test_last_week_resolves_across_month_boundary() -> None:
    with empty_connection() as connection:
        result = tool(connection, datetime(2026, 8, 3, 12, tzinfo=UTC)).run(
            StructuredQueryRequest(
                template="application_list",
                date_window=DateWindowSpec(kind="last_week"),
                timezone="UTC",
            )
        )

    assert result.resolved_date_window is not None
    assert result.resolved_date_window.start_at.isoformat() == "2026-07-27T00:00:00+00:00"
    assert result.resolved_date_window.end_at.isoformat() == "2026-08-03T00:00:00+00:00"


def test_last_week_uses_dst_aware_local_midnights() -> None:
    with empty_connection() as connection:
        result = tool(connection, datetime(2026, 3, 12, 12, tzinfo=UTC)).run(
            StructuredQueryRequest(
                template="application_list",
                date_window=DateWindowSpec(kind="last_week"),
                timezone="America/New_York",
            )
        )

    assert result.resolved_date_window is not None
    assert result.resolved_date_window.start_at.isoformat() == "2026-03-02T05:00:00+00:00"
    assert result.resolved_date_window.end_at.isoformat() == "2026-03-09T04:00:00+00:00"


def test_rolling_days_are_inclusive_local_calendar_days() -> None:
    with empty_connection() as connection:
        result = tool(connection, datetime(2026, 7, 18, 20, tzinfo=UTC)).run(
            StructuredQueryRequest(
                template="application_list",
                date_window=DateWindowSpec(kind="rolling_days", days=3),
                timezone="America/Los_Angeles",
            )
        )

    assert result.resolved_date_window is not None
    assert result.resolved_date_window.start_at.isoformat() == "2026-07-16T07:00:00+00:00"
    assert result.resolved_date_window.end_at.isoformat() == "2026-07-19T07:00:00+00:00"


@pytest.mark.parametrize(
    ("date_window", "start_at", "end_at"),
    (
        (DateWindowSpec(kind="this_week"), "2026-07-13", "2026-07-20"),
        (DateWindowSpec(kind="this_month"), "2026-07-01", "2026-08-01"),
        (DateWindowSpec(kind="last_month"), "2026-06-01", "2026-07-01"),
        (DateWindowSpec(kind="this_year"), "2026-01-01", "2027-01-01"),
        (DateWindowSpec(kind="last_year"), "2025-01-01", "2026-01-01"),
        (DateWindowSpec(kind="calendar_year", year=2024), "2024-01-01", "2025-01-01"),
        (
            DateWindowSpec(
                kind="custom",
                start_date=date(2026, 4, 3),
                end_date_exclusive=date(2026, 4, 9),
            ),
            "2026-04-03",
            "2026-04-09",
        ),
    ),
)
def test_approved_calendar_windows_resolve_exact_bounds(
    date_window: DateWindowSpec,
    start_at: str,
    end_at: str,
) -> None:
    with empty_connection() as connection:
        result = tool(connection).run(
            StructuredQueryRequest(
                template="total_applications",
                date_window=date_window,
                timezone="UTC",
            )
        )

    assert result.resolved_date_window is not None
    assert result.resolved_date_window.start_at.isoformat() == f"{start_at}T00:00:00+00:00"
    assert result.resolved_date_window.end_at.isoformat() == f"{end_at}T00:00:00+00:00"


def test_application_and_company_lists_reconcile_dedupe_and_order() -> None:
    with empty_connection() as connection:
        insert_application(
            connection,
            application_id="app-2",
            company=" ACME ",
            role="Data Engineer",
            first_seen_at="2026-02-02T10:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-1",
            company="Acme",
            role="Backend Engineer",
            first_seen_at="2026-02-02T10:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-3",
            company="Beta",
            role="Backend Engineer",
            first_seen_at="2026-01-01T10:00:00+00:00",
            source="linkedin",
        )
        query_tool = tool(connection)

        applications = query_tool.run(StructuredQueryRequest(template="application_list"))
        companies = query_tool.run(StructuredQueryRequest(template="company_list"))
        filtered = query_tool.run(
            StructuredQueryRequest(
                template="company_list",
                filters=MetricsFilter(source="linkedin", role="backend"),
            )
        )
        repository_count = MetricsRepository(connection).count_total_applications()

    assert [row.values["application_id"] for row in applications.rows] == [
        "app-1",
        "app-2",
        "app-3",
    ]
    assert applications.total_matching_count == repository_count == 3
    assert applications.returned_count == 3
    assert applications.limit == 20
    assert applications.truncated is False
    assert companies.rows[0].values == {
        "company": "acme",
        "application_count": 2,
        "role_titles": ("Backend Engineer", "Data Engineer"),
        "application_ids": ("app-1", "app-2"),
    }
    assert filtered.total_matching_count == 1
    assert filtered.rows[0].label == "beta"


def test_lists_exclude_outreach_only_rows() -> None:
    with empty_connection() as connection:
        insert_application(
            connection,
            application_id="submitted",
            company="Submitted Co",
            role="Engineer",
            first_seen_at="2026-01-01T10:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="outreach",
            company="Outreach Co",
            role="Engineer",
            first_seen_at="2026-01-02T10:00:00+00:00",
        )
        insert_outreach_evidence(connection, application_id="outreach")
        query_tool = tool(connection)

        applications = query_tool.run(StructuredQueryRequest(template="application_list"))
        companies = query_tool.run(StructuredQueryRequest(template="company_list"))

    assert [row.values["application_id"] for row in applications.rows] == ["submitted"]
    assert [row.label for row in companies.rows] == ["submitted co"]


def test_application_list_honors_constrained_requested_limit() -> None:
    with empty_connection() as connection:
        for index in range(101):
            insert_application(
                connection,
                application_id=f"app-{index:03d}",
                company=f"Company {index:03d}",
                role="Engineer",
                first_seen_at="2026-01-01T10:00:00+00:00",
            )

        result = tool(connection).run(StructuredQueryRequest(template="application_list", limit=1))

    assert len(result.rows) == 1
    assert result.total_matching_count == 101
    assert result.returned_count == 1
    assert result.limit == 1
    assert result.truncated is True
    assert result.rows[0].values["application_id"] == "app-000"


def test_busiest_application_month_returns_all_ties_and_empty() -> None:
    with empty_connection() as connection:
        for application_id, first_seen_at in (
            ("jan-1", "2026-01-01T01:00:00+00:00"),
            ("jan-2", "2026-01-20T01:00:00+00:00"),
            ("feb-1", "2026-02-01T01:00:00+00:00"),
            ("feb-2", "2026-02-20T01:00:00+00:00"),
        ):
            insert_application(
                connection,
                application_id=application_id,
                company=application_id,
                role="Engineer",
                first_seen_at=first_seen_at,
            )
        query_tool = tool(connection)
        ties = query_tool.run(
            StructuredQueryRequest(template="busiest_application_month", timezone="UTC")
        )
        connection.execute("DELETE FROM applications")
        empty = query_tool.run(
            StructuredQueryRequest(template="busiest_application_month", timezone="UTC")
        )

    assert [(row.label, row.values["application_count"]) for row in ties.rows] == [
        ("2026-01-01", 2),
        ("2026-02-01", 2),
    ]
    assert empty.rows == ()


def test_busiest_application_month_uses_requested_timezone() -> None:
    with empty_connection() as connection:
        insert_application(
            connection,
            application_id="utc-feb-local-jan",
            company="Boundary Co",
            role="Engineer",
            first_seen_at="2026-02-01T01:00:00+00:00",
        )

        result = tool(connection).run(
            StructuredQueryRequest(
                template="busiest_application_month",
                timezone="America/New_York",
            )
        )

    assert result.rows[0].label == "2026-01-01"


def tool(
    connection: sqlite3.Connection,
    now: datetime = datetime(2026, 7, 18, 12, tzinfo=UTC),
) -> StructuredQueryTool:
    return StructuredQueryTool(
        metrics_repository=MetricsRepository(connection),
        ghost_threshold_days=30,
        clock=lambda: now,
    )


def empty_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    SyntheticFixtureRepository(connection).load_file(SCHEMA_FIXTURE)
    connection.execute("DELETE FROM application_events")
    connection.execute("DELETE FROM email_classifications")
    connection.execute("DELETE FROM raw_emails")
    connection.execute("DELETE FROM applications")
    return connection


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str,
    role: str,
    first_seen_at: str,
    source: str = "company_site",
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at, current_status,
            salary_min, salary_max, currency, location, work_mode, seniority,
            sponsorship, tech_stack, last_activity_at, manual_lock,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'applied', NULL, NULL, NULL, NULL, NULL, NULL,
            'unknown', '[]', ?, 0, ?, ?)
        """,
        (
            application_id,
            company,
            role,
            source,
            first_seen_at,
            first_seen_at,
            first_seen_at,
            first_seen_at,
        ),
    )
    connection.commit()


def insert_outreach_evidence(connection: sqlite3.Connection, *, application_id: str) -> None:
    timestamp = "2026-01-02T10:00:00+00:00"
    connection.execute(
        """
        INSERT INTO raw_emails (
            id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
            body_retention_state, labels, provider, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "outreach-email",
            "outreach-thread",
            "recruiter@example.test",
            "candidate@example.test",
            "Opportunity",
            timestamp,
            "Synthetic outreach.",
            "retained",
            "[]",
            "gmail",
            timestamp,
        ),
    )
    connection.execute(
        """
        INSERT INTO email_classifications (
            email_id, is_job_related, category, confidence, model, prompt_version, classified_at
        ) VALUES (?, 1, 'recruiter_outreach', 1.0, 'test', 'test', ?)
        """,
        ("outreach-email", timestamp),
    )
    connection.execute(
        """
        INSERT INTO application_events (
            id, application_id, email_id, event_type, event_at
        ) VALUES (?, ?, ?, 'response', ?)
        """,
        ("outreach-event", application_id, "outreach-email", timestamp),
    )
    connection.commit()
