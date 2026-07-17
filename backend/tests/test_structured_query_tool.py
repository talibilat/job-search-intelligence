from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import pytest
from app.agent.tools.structured_query import (
    StructuredQueryRequest,
    StructuredQueryTemplate,
    StructuredQueryTool,
)
from app.db.repositories import MetricsRepository, SyntheticFixtureRepository
from app.models.records import (
    ApplicationRecord,
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_FIXTURE_PATH = BACKEND_ROOT / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"
NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def test_structured_query_tool_answers_total_applications_from_metrics_repository() -> None:
    with fixture_connection() as connection:
        tool = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        )

        result = tool.run(StructuredQueryRequest(template="total_applications"))

    assert result.tool == "structured_query"
    assert result.template == "total_applications"
    assert result.rows[0].label == "total_applications"
    assert result.rows[0].values == {"application_count": 1}


def test_structured_query_tool_answers_summary_counts_from_metrics_repository() -> None:
    with fixture_connection() as connection:
        tool = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        )

        result = tool.run(StructuredQueryRequest(template="summary_counts"))

    assert result.template == "summary_counts"
    assert result.rows[0].values == {
        "total_applications": 1,
        "distinct_company_count": 1,
        "offers_received": 0,
        "ghosted_applications": 0,
        "rejected_applications": 1,
        "interview_invitation_count": 0,
        "human_response_count": 1,
        "silent_count": 0,
    }


def test_structured_query_tool_answers_rate_and_funnel_templates() -> None:
    with fixture_connection() as connection:
        tool = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        )

        rates = tool.run(StructuredQueryRequest(template="rates"))
        funnel = tool.run(StructuredQueryRequest(template="funnel"))

    assert rates.rows[0].label == "response"
    assert rates.rows[0].values == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert [(row.label, row.values["count"]) for row in funnel.rows] == [
        ("applied", 1),
        ("screen", 1),
        ("interview", 0),
        ("final", 0),
        ("offer", 0),
    ]


def test_structured_query_tool_answers_timing_template() -> None:
    with fixture_connection() as connection:
        result = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        ).run(StructuredQueryRequest(template="timing"))

    assert [(row.label, row.values) for row in result.rows] == [
        (
            "time_to_first_response",
            {"application_count": 1, "average_hours": 339.5},
        ),
        (
            "time_to_rejection",
            {"application_count": 1, "average_hours": 339.5},
        ),
    ]


def test_structured_query_tool_answers_application_timeseries_template() -> None:
    with fixture_connection() as connection:
        result = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        ).run(StructuredQueryRequest(template="application_timeseries"))

    assert [(row.label, row.values) for row in result.rows] == [
        (
            "2026-07-04",
            {"period_start": "2026-07-04", "application_count": 1},
        )
    ]


def test_structured_query_tool_answers_response_rate_timeseries_template() -> None:
    with fixture_connection() as connection:
        result = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        ).run(StructuredQueryRequest(template="response_rate_timeseries"))

    assert [(row.label, row.values) for row in result.rows] == [
        (
            "2026-07-04",
            {
                "period_start": "2026-07-04",
                "response_count": 1,
                "application_count": 1,
                "response_rate": 1.0,
            },
        )
    ]


def test_structured_query_tool_requires_breakdown_dimension() -> None:
    with pytest.raises(ValidationError, match="breakdown_dimension is required"):
        StructuredQueryRequest(template="breakdown")


def test_structured_query_tool_answers_whitelisted_breakdown_dimension() -> None:
    with fixture_connection() as connection:
        tool = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=30,
            clock=lambda: NOW,
        )

        result = tool.run(StructuredQueryRequest(template="breakdown", breakdown_dimension="role"))

    assert result.template == "breakdown"
    assert result.rows[0].label == "backend engineer"
    assert result.rows[0].values["application_count"] == 1
    assert result.rows[0].values["response_rate"] == 1.0


def test_structured_query_request_exposes_no_raw_sql_field() -> None:
    assert "sql" not in StructuredQueryRequest.model_fields
    with pytest.raises(ValidationError):
        StructuredQueryRequest.model_validate({"template": "arbitrary_sql", "sql": "select 1"})


def test_structured_query_template_is_explicit_whitelist() -> None:
    assert set(get_args(StructuredQueryTemplate)) == {
        "total_applications",
        "summary_counts",
        "rates",
        "funnel",
        "timing",
        "application_timeseries",
        "response_rate_timeseries",
        "breakdown",
        "live_applications",
    }


def test_live_applications_use_follow_up_policy_not_ghost_threshold() -> None:
    class ApplicationReader:
        def list_applications(
            self,
            *,
            current_status: ApplicationStatus | None = None,
            source: ApplicationSource | None = None,
            sponsorship: SponsorshipStatus | None = None,
            first_seen_from: str | None = None,
            first_seen_to: str | None = None,
            role: str | None = None,
            salary_min: int | None = None,
            salary_max: int | None = None,
            work_mode: WorkMode | None = None,
        ) -> list[ApplicationRecord]:
            return [
                application("waiting", "Waiting Co", "applied", "2026-07-28T12:00:00Z"),
                application("overdue", "Overdue Co", "in_review", "2026-07-25T12:00:00Z"),
                application("interview", "Interview Co", "interview", "2026-07-20T12:00:00Z"),
                application("assessment", "Assessment Co", "assessment", "2026-07-20T12:00:00Z"),
                application("offer", "Offer Co", "offer", "2026-07-20T12:00:00Z"),
                application("rejected", "Rejected Co", "rejected", "2026-07-20T12:00:00Z"),
            ]

    with fixture_connection() as connection:
        result = StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            application_reader=ApplicationReader(),
            ghost_threshold_days=60,
            follow_up_threshold_days=7,
            clock=lambda: NOW,
        ).run(StructuredQueryRequest(template="live_applications"))

    assert [row.label for row in result.rows] == ["Waiting Co", "Overdue Co", "Interview Co"]
    assert [row.values["days_waiting"] for row in result.rows] == [4, 7, 12]
    assert [row.values["follow_up_due"] for row in result.rows] == [False, True, True]
    assert all(row.values["follow_up_threshold_days"] == 7 for row in result.rows)


def test_live_applications_forward_typed_filters_to_application_reader() -> None:
    class ApplicationReader:
        received: dict[str, object] = {}

        def list_applications(
            self,
            *,
            current_status: ApplicationStatus | None = None,
            source: ApplicationSource | None = None,
            sponsorship: SponsorshipStatus | None = None,
            first_seen_from: str | None = None,
            first_seen_to: str | None = None,
            role: str | None = None,
            salary_min: int | None = None,
            salary_max: int | None = None,
            work_mode: WorkMode | None = None,
        ) -> list[ApplicationRecord]:
            self.received = {
                "current_status": current_status,
                "source": source,
                "sponsorship": sponsorship,
                "first_seen_from": first_seen_from,
                "first_seen_to": first_seen_to,
                "role": role,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "work_mode": work_mode,
            }
            return []

    reader = ApplicationReader()
    with fixture_connection() as connection:
        StructuredQueryTool(
            metrics_repository=MetricsRepository(connection),
            application_reader=reader,
            ghost_threshold_days=30,
            clock=lambda: NOW,
        ).run(
            StructuredQueryRequest.model_validate(
                {
                    "template": "live_applications",
                    "filters": {
                        "status": "in_review",
                        "source": "linkedin",
                        "sponsorship": "offered",
                        "first_seen_from": "2026-07-01T00:00:00Z",
                        "first_seen_to": "2026-07-31T23:59:59Z",
                        "role": "Platform Engineer",
                        "salary_min": 100_000,
                        "salary_max": 150_000,
                        "work_mode": "remote",
                    },
                }
            )
        )

    assert reader.received == {
        "current_status": "in_review",
        "source": "linkedin",
        "sponsorship": "offered",
        "first_seen_from": "2026-07-01T00:00:00+00:00",
        "first_seen_to": "2026-07-31T23:59:59+00:00",
        "role": "Platform Engineer",
        "salary_min": 100_000,
        "salary_max": 150_000,
        "work_mode": "remote",
    }


def application(
    application_id: str,
    company: str,
    status: str,
    last_activity_at: str,
) -> ApplicationRecord:
    return ApplicationRecord.model_validate(
        {
            "id": application_id,
            "company": company,
            "role_title": "Engineer",
            "source": "company_site",
            "first_seen_at": last_activity_at,
            "current_status": status,
            "currency": None,
            "location": None,
            "work_mode": None,
            "seniority": None,
            "sponsorship": "unknown",
            "tech_stack": [],
            "last_activity_at": last_activity_at,
            "manual_lock": False,
            "created_at": last_activity_at,
            "updated_at": last_activity_at,
        }
    )


def fixture_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    SyntheticFixtureRepository(connection).load_file(SYNTHETIC_FIXTURE_PATH)
    return connection
