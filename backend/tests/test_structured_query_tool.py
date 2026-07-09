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
        "breakdown",
    }


def fixture_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    SyntheticFixtureRepository(connection).load_file(SYNTHETIC_FIXTURE_PATH)
    return connection
