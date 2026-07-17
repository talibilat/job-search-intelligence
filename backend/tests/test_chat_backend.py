from __future__ import annotations

import asyncio
import json as jsonlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from app.agent.chat_graph import _structured_request, route_question
from app.api.dependencies import get_llm_provider
from app.config import AppSettings, get_settings
from app.db.engine import load_sqlite_vec_sync
from app.db.repositories import ApplicationRepository
from app.main import create_app
from app.providers.llm import (
    LLMEmbedding,
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMGenerationRequest,
    LLMProviderHealthCheckRequest,
)
from app.security import SecretRef, SecretStore
from app.services.wipe_data import wipe_local_data
from fastapi.testclient import TestClient
from pydantic import SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class FakeChatProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.embedding_inputs: list[tuple[str, ...]] = []

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        self.embedding_inputs.append(request.inputs)
        return LLMEmbeddingResponse(
            model=request.model or "fake-embedding",
            embeddings=tuple(
                LLMEmbedding(index=index, embedding=_embedding_for_text(text))
                for index, text in enumerate(request.inputs)
            ),
        )

    async def generate(self, request: LLMGenerationRequest) -> None:
        raise AssertionError(f"chat must not ask an LLM to restate tool facts: {request!r}")

    async def health_check(self, request: LLMProviderHealthCheckRequest) -> None:
        raise AssertionError(f"chat request must not perform a readiness probe: {request!r}")


class EmptySecretStore(SecretStore):
    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        return None

    async def delete_secret(self, ref: SecretRef) -> None:
        return None


@pytest.mark.parametrize(
    ("question", "expected"),
    (
        ("What exactly did the recruiter at Acme say?", "content"),
        ("Show me every rejection email that mentioned experience", "content"),
        ("Who am I waiting on and who is overdue for a follow-up?", "quantitative"),
        ("How many applications and what exactly did recruiters say?", "mixed"),
        ("Tell me anything useful about my Acme search", "content"),
    ),
)
def test_q47_to_q50_representative_questions_route_without_sql(
    question: str,
    expected: str,
) -> None:
    assert route_question(question) == expected


@pytest.mark.parametrize(
    ("question", "expected_from", "expected_to"),
    (
        (
            "How many applications this week?",
            datetime(2026, 7, 13, tzinfo=UTC),
            datetime(2026, 7, 19, 23, 59, 59, 999999, tzinfo=UTC),
        ),
        (
            "How many applications this month?",
            datetime(2026, 7, 1, tzinfo=UTC),
            datetime(2026, 7, 31, 23, 59, 59, 999999, tzinfo=UTC),
        ),
        (
            "How many applications this year?",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
        ),
    ),
)
def test_structured_chat_maps_relative_windows_to_typed_metric_filters(
    question: str,
    expected_from: datetime,
    expected_to: datetime,
) -> None:
    request = _structured_request(
        question,
        anchor_at=datetime(2026, 7, 17, 15, 30, tzinfo=UTC),
    )

    assert request.template == "summary_counts"
    assert request.filters is not None
    assert request.filters.first_seen_from == expected_from
    assert request.filters.first_seen_to == expected_to


@pytest.mark.parametrize(
    "question",
    (
        "How many applications in 2025?",
        "How many jobs did I apply to during 2025?",
        "How many roles did I apply for in 2025?",
    ),
)
def test_structured_chat_maps_explicit_calendar_year_to_typed_metric_filters(
    question: str,
) -> None:
    request = _structured_request(question)

    assert request.template == "summary_counts"
    assert request.filters is not None
    assert request.filters.first_seen_from == datetime(2025, 1, 1, tzinfo=UTC)
    assert request.filters.first_seen_to == datetime(
        2025,
        12,
        31,
        23,
        59,
        59,
        999999,
        tzinfo=UTC,
    )


def test_structured_chat_composes_source_and_relative_window_filters() -> None:
    request = _structured_request(
        "How many LinkedIn applications this month?",
        anchor_at=datetime(2026, 7, 17, 15, 30, tzinfo=UTC),
    )

    assert request.filters is not None
    assert request.filters.source == "linkedin"
    assert request.filters.first_seen_from == datetime(2026, 7, 1, tzinfo=UTC)
    assert request.filters.first_seen_to == datetime(
        2026,
        7,
        31,
        23,
        59,
        59,
        999999,
        tzinfo=UTC,
    )


@pytest.mark.parametrize(
    "question",
    (
        "What is my conversion rate for LinkedIn vs company site?",
        "Compare LinkedIn with referrals.",
        "How do company website and Indeed applications convert?",
    ),
)
def test_structured_chat_preserves_unfiltered_source_comparisons(question: str) -> None:
    request = _structured_request(question)

    assert route_question(question) == "quantitative"
    assert request.template == "breakdown"
    assert request.breakdown_dimension == "source"
    assert request.filters is None


def test_structured_chat_preserves_filters_for_live_application_queries() -> None:
    request = _structured_request(
        "Who am I waiting on from LinkedIn this month?",
        anchor_at=datetime(2026, 7, 17, 15, 30, tzinfo=UTC),
    )

    assert request.template == "live_applications"
    assert request.filters is not None
    assert request.filters.source == "linkedin"
    assert request.filters.first_seen_from == datetime(2026, 7, 1, tzinfo=UTC)
    assert request.filters.first_seen_to == datetime(
        2026,
        7,
        31,
        23,
        59,
        59,
        999999,
        tzinfo=UTC,
    )


@pytest.mark.parametrize(
    ("question", "expected_work_mode"),
    (
        ("How many remote applications?", "remote"),
        ("How many hybrid roles did I apply to?", "hybrid"),
        ("How many on-site applications?", "onsite"),
    ),
)
def test_structured_chat_maps_work_modes_to_typed_metric_filters(
    question: str,
    expected_work_mode: str,
) -> None:
    request = _structured_request(question)

    assert request.filters is not None
    assert request.filters.work_mode == expected_work_mode


def test_structured_chat_preserves_unfiltered_work_mode_comparisons() -> None:
    request = _structured_request("How do remote vs hybrid roles convert?")

    assert request.template == "breakdown"
    assert request.breakdown_dimension == "work_mode"
    assert request.filters is None


@pytest.mark.parametrize(
    ("question", "expected_sponsorship"),
    (
        ("How many applications offered sponsorship?", "offered"),
        ("How many applications did not offer sponsorship?", "not_offered"),
        ("How many applications have unknown sponsorship?", "unknown"),
    ),
)
def test_structured_chat_maps_sponsorship_to_typed_metric_filters(
    question: str,
    expected_sponsorship: str,
) -> None:
    request = _structured_request(question)

    assert request.filters is not None
    assert request.filters.sponsorship == expected_sponsorship


def test_structured_chat_preserves_unfiltered_sponsorship_comparisons() -> None:
    request = _structured_request("How do offered sponsorship vs non-sponsorship roles convert?")

    assert request.template == "breakdown"
    assert request.breakdown_dimension == "sponsorship"
    assert request.filters is None


@pytest.mark.parametrize(
    ("question", "expected_status"),
    (
        ("How many applications are currently in review?", "in_review"),
        ("How many applications are under review?", "in_review"),
        ("How many applications are in the assessment stage?", "assessment"),
        ("How many applications are currently interviewing?", "interview"),
        ("How many applications are at the offer stage?", "offer"),
        ("How many rejected applications do I have?", "rejected"),
        ("How many ghosted applications do I have?", "ghosted"),
        ("How many withdrawn applications do I have?", "withdrawn"),
    ),
)
def test_structured_chat_maps_current_status_to_typed_metric_filter(
    question: str,
    expected_status: str,
) -> None:
    request = _structured_request(question)

    assert request.template == "summary_counts"
    assert request.filters is not None
    assert request.filters.status == expected_status


@pytest.mark.parametrize(
    "question",
    (
        "How many jobs have I applied to?",
        "How many interview invitations have I received?",
        "How many offers have I received?",
        "How many applications are in review or currently interviewing?",
    ),
)
def test_structured_chat_does_not_infer_ambiguous_current_status(question: str) -> None:
    request = _structured_request(question)

    assert request.filters is None or request.filters.status is None


def test_structured_chat_composes_status_source_and_relative_window_filters() -> None:
    request = _structured_request(
        "How many LinkedIn applications are currently in review this month?",
        anchor_at=datetime(2026, 7, 17, 15, 30, tzinfo=UTC),
    )

    assert request.filters is not None
    assert request.filters.status == "in_review"
    assert request.filters.source == "linkedin"
    assert request.filters.first_seen_from == datetime(2026, 7, 1, tzinfo=UTC)
    assert request.filters.first_seen_to == datetime(
        2026,
        7,
        31,
        23,
        59,
        59,
        999999,
        tzinfo=UTC,
    )


@pytest.mark.parametrize(
    ("question", "expected_min", "expected_max"),
    (
        ("How many applications had a salary 100k to 150k?", 100_000, 150_000),
        ("How many roles had a salary between £90,000 and £120,000?", 90_000, 120_000),
        ("How many applications had a salary at least $125k?", 125_000, None),
        ("How many applications had a salary under 80k?", None, 80_000),
    ),
)
def test_structured_chat_maps_salary_language_to_typed_metric_filters(
    question: str,
    expected_min: int | None,
    expected_max: int | None,
) -> None:
    request = _structured_request(question)

    assert request.filters is not None
    assert request.filters.salary_min == expected_min
    assert request.filters.salary_max == expected_max


def test_structured_chat_does_not_filter_salary_breakdown_without_amounts() -> None:
    request = _structured_request("How do my salary bands convert?")

    assert request.template == "breakdown"
    assert request.breakdown_dimension == "salary"
    assert request.filters is None


@pytest.mark.parametrize(
    ("question", "expected_role"),
    (
        ("How many applications for Data Scientist roles?", "data scientist"),
        ('How many applications have the role "Platform Engineer"?', "platform engineer"),
        ("Count applications where the job title is 'Product Designer'.", "product designer"),
    ),
)
def test_structured_chat_maps_explicit_role_phrases_to_typed_metric_filter(
    question: str,
    expected_role: str,
) -> None:
    request = _structured_request(question)

    assert request.filters is not None
    assert request.filters.role == expected_role


def test_structured_chat_does_not_treat_work_mode_as_role() -> None:
    request = _structured_request("How many applications for remote roles?")

    assert request.filters is not None
    assert request.filters.role is None
    assert request.filters.work_mode == "remote"


def test_chat_api_relative_month_count_reconciles_with_filtered_metrics(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-current-month", company="Current")
        insert_application(connection, application_id="app-old", company="Old")
        connection.execute(
            "UPDATE applications SET first_seen_at = ? WHERE id = ?",
            (now.isoformat(), "app-current-month"),
        )
        connection.execute(
            "UPDATE applications SET first_seen_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", "app-old"),
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    metric_response = client.get(
        "/metrics/summary",
        params={
            "first_seen_from": month_start.isoformat(),
            "first_seen_to": (next_month - datetime.resolution).isoformat(),
        },
    )
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many applications this month?"},
    )

    assert metric_response.status_code == 200
    assert chat_response.status_code == 200
    chat_values = chat_response.json()["tool_outputs"][0]["rows"][0]["values"]
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_calendar_year_count_reconciles_with_filtered_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-2025",
            company="Prior Year Company",
        )
        insert_application(
            connection,
            application_id="app-2026",
            company="Current Year Company",
        )
        connection.execute(
            "UPDATE applications SET first_seen_at = ? WHERE id = ?",
            ("2025-06-15T10:00:00+00:00", "app-2025"),
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get(
        "/metrics/summary",
        params={
            "first_seen_from": "2025-01-01T00:00:00+00:00",
            "first_seen_to": "2025-12-31T23:59:59.999999+00:00",
        },
    )
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many applications in 2025?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    chat_values = chat_body["tool_outputs"][0]["rows"][0]["values"]
    assert chat_body["route"] == "quantitative"
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_source_count_reconciles_with_filtered_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-company-site",
            company="Company Site Source",
        )
        insert_application(
            connection,
            application_id="app-linkedin",
            company="LinkedIn Source",
            source="linkedin",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get("/metrics/summary", params={"source": "linkedin"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many LinkedIn applications have I submitted?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_values = chat_response.json()["tool_outputs"][0]["rows"][0]["values"]
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_source_comparison_reconciles_with_breakdown_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-company-site",
            company="Company Site Source",
        )
        insert_application(
            connection,
            application_id="app-linkedin",
            company="LinkedIn Source",
            source="linkedin",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    metric_response = client.get("/metrics/breakdown", params={"dimension": "source"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "What is my conversion rate for LinkedIn vs company site?"},
    )

    assert metric_response.status_code == 200
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    assert chat_body["route"] == "quantitative"
    assert chat_body["tool_outputs"][0]["template"] == "breakdown"
    assert chat_body["tool_outputs"][0]["rows"] == [
        {
            "label": row["value"],
            "values": {key: value for key, value in row.items() if key != "value"},
        }
        for row in metric_response.json()["rows"]
    ]
    assert provider.embedding_inputs == []


def test_chat_api_work_mode_count_reconciles_with_filtered_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-remote",
            company="Remote Company",
            work_mode="remote",
        )
        insert_application(
            connection,
            application_id="app-onsite",
            company="Onsite Company",
            work_mode="onsite",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get("/metrics/summary", params={"work_mode": "remote"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many remote applications have I submitted?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_values = chat_response.json()["tool_outputs"][0]["rows"][0]["values"]
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_sponsorship_count_reconciles_with_filtered_metrics(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-sponsored",
            company="Sponsored Company",
            sponsorship="offered",
        )
        insert_application(
            connection,
            application_id="app-unknown-sponsorship",
            company="Unknown Sponsorship Company",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get("/metrics/summary", params={"sponsorship": "offered"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many applications offered sponsorship?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_values = chat_response.json()["tool_outputs"][0]["rows"][0]["values"]
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_status_count_reconciles_with_filtered_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-in-review",
            company="Review Company",
        )
        insert_application(
            connection,
            application_id="app-interviewing",
            company="Interview Company",
            current_status="interview",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get("/metrics/summary", params={"status": "in_review"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many applications are currently in review?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    chat_values = chat_body["tool_outputs"][0]["rows"][0]["values"]
    assert chat_body["route"] == "quantitative"
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_salary_count_reconciles_with_filtered_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-in-band",
            company="In Band Company",
            salary_min=110_000,
            salary_max=140_000,
        )
        insert_application(
            connection,
            application_id="app-outside-band",
            company="Outside Band Company",
            salary_min=160_000,
            salary_max=190_000,
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get(
        "/metrics/summary",
        params={"salary_min": 100_000, "salary_max": 150_000},
    )
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many applications had a salary 100k to 150k?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    chat_values = chat_body["tool_outputs"][0]["rows"][0]["values"]
    assert chat_body["route"] == "quantitative"
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_role_count_reconciles_with_filtered_metrics(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-data-scientist",
            company="Data Company",
            role_title="Data Scientist",
        )
        insert_application(
            connection,
            application_id="app-platform-engineer",
            company="Platform Company",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    unfiltered_response = client.get("/metrics/summary")
    metric_response = client.get("/metrics/summary", params={"role": "Data Scientist"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "How many applications for Data Scientist roles?"},
    )

    assert metric_response.status_code == 200
    assert unfiltered_response.json()["total_applications"] == 2
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    chat_values = chat_body["tool_outputs"][0]["rows"][0]["values"]
    assert chat_body["route"] == "quantitative"
    assert metric_response.json()["total_applications"] == 1
    assert chat_values["total_applications"] == metric_response.json()["total_applications"]
    assert provider.embedding_inputs == []


def test_chat_api_filters_waiting_applications_by_source(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-linkedin",
            company="LinkedIn Live Co",
            source="linkedin",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    application_response = client.get("/applications", params={"source": "linkedin"})
    chat_response = post_chat(
        client,
        "/chat",
        json={"message": "Who am I waiting on from LinkedIn?"},
    )

    assert application_response.status_code == 200
    assert [application["id"] for application in application_response.json()] == ["app-linkedin"]
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    rows = chat_body["tool_outputs"][0]["rows"]
    assert chat_body["route"] == "quantitative"
    assert [row["values"]["application_id"] for row in rows] == ["app-linkedin"]
    assert chat_body["citations"][0]["application_id"] == "app-linkedin"
    assert "Acme" not in chat_body["answer"]
    assert provider.embedding_inputs == []


def test_chat_api_reconciles_metrics_retrieves_citations_and_persists_history(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    metric_response = client.get("/metrics/summary")
    quantitative = post_chat(
        client,
        "/chat",
        json={"conversation_id": "q-count", "message": "How many jobs have I applied to?"},
    )

    assert metric_response.status_code == 200
    assert quantitative.status_code == 200
    quantitative_body = quantitative.json()
    assert quantitative_body["route"] == "quantitative"
    assert quantitative_body["tool_outputs"][0]["template"] == "summary_counts"
    assert (
        quantitative_body["tool_outputs"][0]["rows"][0]["values"]["total_applications"]
        == metric_response.json()["total_applications"]
    )
    assert quantitative_body["citations"] == [
        {
            "citation_id": "metric:summary_counts",
            "source": "metric",
            "email_public_id": None,
            "application_id": None,
            "metric_template": "summary_counts",
            "subject": None,
            "sent_at": None,
            "snippet": None,
        }
    ]
    assert [increment["type"] for increment in quantitative_body["increments"]] == [
        "route",
        "tool",
        "answer",
    ]
    assert [event["type"] for event in quantitative.events] == ["route", "tool", "complete"]
    assert quantitative.response.headers["cache-control"] == "no-cache"
    assert quantitative.response.headers["x-accel-buffering"] == "no"
    assert provider.embedding_inputs == []

    source_breakdown_response = client.get("/metrics/breakdown", params={"dimension": "source"})
    source_breakdown = post_chat(
        client,
        "/chat",
        json={
            "conversation_id": "q-source-breakdown",
            "message": "Which sources have the best conversion rate?",
        },
    )

    assert source_breakdown_response.status_code == 200
    assert source_breakdown.status_code == 200
    source_breakdown_body = source_breakdown.json()
    assert source_breakdown_body["route"] == "quantitative"
    assert source_breakdown_body["tool_outputs"][0]["template"] == "breakdown"
    assert source_breakdown_body["tool_outputs"][0]["rows"] == [
        {
            "label": row["value"],
            "values": row,
        }
        for row in source_breakdown_response.json()["rows"]
    ]
    assert source_breakdown_body["citations"][0]["citation_id"] == "metric:breakdown"
    assert provider.embedding_inputs == []

    content = post_chat(
        client,
        "/chat",
        json={
            "conversation_id": "q-content",
            "message": "What exactly did the recruiter at Acme say in the last email?",
        },
    )

    assert content.status_code == 200
    content_body = content.json()
    assert content_body["route"] == "content"
    assert "Technical interview moved to Friday" in content_body["answer"]
    assert content_body["citations"][0]["source"] == "email"
    assert content_body["citations"][0]["application_id"] == "app-acme"
    assert content_body["citations"][0]["email_public_id"]
    assert content_body["citations"][0]["citation_id"].startswith("email:")
    with sqlite3.connect(database_path) as connection:
        load_sqlite_vec_sync(connection, None)
        assert connection.execute("SELECT DISTINCT email_id FROM email_chunks").fetchall() == [
            ("email-job",)
        ]
    embedded_body_batches = [inputs for inputs in provider.embedding_inputs if len(inputs) > 1]
    assert embedded_body_batches == []
    assert any(
        inputs == ("Acme recruiter: Technical interview moved to Friday.",)
        for inputs in provider.embedding_inputs
    )
    embedded_texts = [text for batch in provider.embedding_inputs for text in batch]
    assert all("private shopping receipt" not in text for text in embedded_texts)
    assert all("debug-only body" not in text for text in embedded_texts)

    mixed = post_chat(
        client,
        "/chat",
        json={
            "conversation_id": "q-mixed",
            "message": "How many applications and what exactly did the Acme recruiter say?",
        },
    )

    assert mixed.status_code == 200
    assert mixed.json()["route"] == "mixed"
    assert [output["tool"] for output in mixed.json()["tool_outputs"]] == [
        "structured_query",
        "semantic_search",
    ]
    assert {citation["source"] for citation in mixed.json()["citations"]} == {
        "metric",
        "email",
    }
    assert (
        provider.embedding_inputs.count(("Acme recruiter: Technical interview moved to Friday.",))
        == 1
    )

    waiting = post_chat(
        client,
        "/chat",
        json={
            "conversation_id": "q-waiting",
            "message": "Who am I waiting on and who is overdue for a follow-up?",
        },
    )
    assert waiting.status_code == 200
    waiting_body = waiting.json()
    assert waiting_body["route"] == "quantitative"
    assert waiting_body["tool_outputs"][0]["template"] == "live_applications"
    assert waiting_body["answer"].startswith("Waiting on: Acme - Platform Engineer")
    assert "[application:app-acme]" in waiting_body["answer"]
    assert "Overdue for follow-up:" in waiting_body["answer"]
    assert waiting_body["citations"][0] == {
        "citation_id": "application:app-acme",
        "source": "application",
        "email_public_id": None,
        "application_id": "app-acme",
        "metric_template": None,
        "subject": None,
        "sent_at": None,
        "snippet": None,
    }

    history = client.get("/chat/history", params={"conversation_id": "q-mixed"})
    assert history.status_code == 200
    assert [message["role"] for message in history.json()["messages"]] == [
        "user",
        "tool",
        "tool",
        "assistant",
    ]
    assistant = history.json()["messages"][-1]
    assert {citation["source"] for citation in assistant["citations_json"]} == {
        "metric",
        "email",
    }
    assert [output["tool"] for output in assistant["tool_outputs_json"]] == [
        "structured_query",
        "semantic_search",
    ]


def test_chat_index_removes_ineligible_vectors_and_refuses_unsupported_content(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)
    first = post_chat(client, "/chat", json={"message": "What exactly did Acme say?"})
    assert first.status_code == 200
    assert first.json()["citations"]

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE email_classifications SET is_job_related = 0 WHERE email_id = ?",
            ("email-job",),
        )
        connection.commit()

    refused = post_chat(client, "/chat", json={"message": "What exactly did Acme say?"})

    assert refused.status_code == 200
    assert refused.json()["citations"] == []
    assert "cannot answer" in refused.json()["answer"]
    with sqlite3.connect(database_path) as connection:
        load_sqlite_vec_sync(connection, None)
        assert connection.execute("SELECT COUNT(*) FROM email_chunks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM email_chunk_index_state").fetchone()[0] == 0


def test_q47_last_email_uses_latest_company_evidence_not_nearest_vector(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(
            connection,
            email_id="email-job-old",
            subject="Earlier recruiter update",
            body="Acme recruiter discussed a historical perfect match.",
            retention="retained",
            sent_at="2026-06-01T10:00:00+00:00",
        )
        insert_classification(connection, "email-job-old", is_job_related=True)
        connection.execute(
            """
            INSERT INTO application_events (
                id, application_id, email_id, event_type, event_at, extract_note
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "event-acme-old",
                "app-acme",
                "email-job-old",
                "response",
                "2026-06-01T10:00:00+00:00",
                "Earlier recruiter response",
            ),
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    response = post_chat(
        client,
        "/chat",
        json={"message": "What exactly did the recruiter at Acme say in the last email?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Technical interview moved to Friday" in body["answer"]
    assert "historical perfect match" not in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["subject"] == "Interview update"
    assert provider.embedding_inputs == [
        ("Acme recruiter discussed a historical perfect match.",),
        ("Acme recruiter: Technical interview moved to Friday.",),
    ]


def test_q47_last_email_includes_newer_indexed_message_from_application_thread(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE raw_emails SET thread_id = ? WHERE id = ?",
            ("thread-acme", "email-job"),
        )
        insert_raw_email(
            connection,
            email_id="email-job-follow-up",
            thread_id="thread-acme",
            subject="Friday interview details",
            body="Acme recruiter: Please bring your architecture examples to Friday's interview.",
            retention="retained",
            sent_at="2026-06-06T10:00:00+00:00",
        )
        insert_classification(
            connection,
            "email-job-follow-up",
            is_job_related=True,
            category="follow_up",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    response = post_chat(
        client,
        "/chat",
        json={"message": "What exactly did the recruiter at Acme say in the last email?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "bring your architecture examples" in body["answer"]
    assert "Technical interview moved" not in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["subject"] == "Friday interview details"
    assert body["citations"][0]["application_id"] == "app-acme"
    assert provider.embedding_inputs == [
        ("Acme recruiter: Technical interview moved to Friday.",),
        ("Acme recruiter: Please bring your architecture examples to Friday's interview.",),
    ]


def test_q48_every_rejection_returns_all_exact_matches_despite_retrieval_limit(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(
            connection,
            email_id="email-rejection-one",
            subject="Application outcome",
            body="We need more production experience for this position.",
            retention="retained",
            sent_at="2026-06-06T10:00:00+00:00",
        )
        insert_classification(
            connection,
            "email-rejection-one",
            is_job_related=True,
            category="rejection",
        )
        insert_raw_email(
            connection,
            email_id="email-rejection-two",
            subject="Role update",
            body="Another candidate had more leadership experience.",
            retention="retained",
            sent_at="2026-06-07T10:00:00+00:00",
        )
        insert_classification(
            connection,
            "email-rejection-two",
            is_job_related=True,
            category="rejection",
        )
        insert_raw_email(
            connection,
            email_id="email-outreach-experience",
            subject="New role",
            body="Your platform experience looks relevant to our opening.",
            retention="retained",
            sent_at="2026-06-08T10:00:00+00:00",
        )
        insert_classification(
            connection,
            "email-outreach-experience",
            is_job_related=True,
            category="recruiter_outreach",
        )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    response = post_chat(
        client,
        "/chat",
        json={
            "message": "Show me every rejection email that mentioned experience.",
            "retrieval_limit": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["citations"]) == 2
    assert {citation["subject"] for citation in body["citations"]} == {
        "Application outcome",
        "Role update",
    }
    assert "production experience" in body["answer"]
    assert "leadership experience" in body["answer"]
    assert "platform experience" not in body["answer"]
    assert (
        "Show me every rejection email that mentioned experience.",
    ) not in provider.embedding_inputs


def test_q48_every_company_returns_distinct_companies_with_citations(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-beta", company="Beta")
        insert_application(connection, application_id="app-gamma", company="Gamma")
        sources = (
            ("email-acme-sponsorship-one", "app-acme", "Acme offers visa sponsorship."),
            ("email-acme-sponsorship-two", "app-acme", "Sponsorship is available at Acme."),
            ("email-beta-sponsorship", "app-beta", "Beta can discuss sponsorship."),
            ("email-gamma-location", "app-gamma", "Gamma requires hybrid attendance."),
        )
        for index, (email_id, application_id, body) in enumerate(sources):
            is_event_neutral_follow_up = email_id == "email-acme-sponsorship-two"
            insert_raw_email(
                connection,
                email_id=email_id,
                subject=f"Role detail {index}",
                body=body,
                retention="retained",
                sent_at=f"2026-06-{10 + index:02d}T10:00:00+00:00",
                thread_id="thread-acme" if application_id == "app-acme" else None,
            )
            insert_classification(
                connection,
                email_id,
                is_job_related=True,
                category="follow_up" if is_event_neutral_follow_up else None,
            )
            if is_event_neutral_follow_up:
                continue
            connection.execute(
                """
                INSERT INTO application_events (
                    id, application_id, email_id, event_type, event_at, extract_note
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"event-{email_id}",
                    application_id,
                    email_id,
                    "response",
                    f"2026-06-{10 + index:02d}T10:00:00+00:00",
                    "Role detail",
                ),
            )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    response = post_chat(
        client,
        "/chat",
        json={
            "message": "Show me every company that mentioned sponsorship.",
            "retrieval_limit": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["citations"]) == 2
    assert body["answer"].startswith("Companies mentioning the requested term:")
    assert body["answer"].count("Acme") == 1
    assert body["answer"].count("Beta") == 1
    assert "Gamma" not in body["answer"]
    assert {citation["subject"] for citation in body["citations"]} == {
        "Role detail 1",
        "Role detail 2",
    }
    assert {citation["application_id"] for citation in body["citations"]} == {
        "app-acme",
        "app-beta",
    }
    assert ("Show me every company that mentioned sponsorship.",) not in provider.embedding_inputs


def test_chat_index_reconciles_all_eligible_emails_across_configured_batches(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    seed_chat_sources(database_path)
    with sqlite3.connect(database_path) as connection:
        for index in range(2):
            email_id = f"email-rejection-{index}"
            insert_raw_email(
                connection,
                email_id=email_id,
                subject=f"Application outcome {index}",
                body=f"Rejection {index} mentioned distributed systems experience.",
                retention="retained",
                sent_at=f"2026-06-0{6 + index}T10:00:00+00:00",
            )
            insert_classification(
                connection,
                email_id,
                is_job_related=True,
                category="rejection",
            )
        connection.commit()
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider, index_batch_size=1)

    first = post_chat(
        client,
        "/chat",
        json={"message": "Show me every rejection email that mentioned experience."},
    )

    assert first.status_code == 200
    assert {citation["subject"] for citation in first.json()["citations"]} == {
        "Application outcome 0",
        "Application outcome 1",
    }
    with sqlite3.connect(database_path) as connection:
        load_sqlite_vec_sync(connection, None)
        assert connection.execute(
            "SELECT email_id FROM email_chunk_index_state ORDER BY email_id"
        ).fetchall() == [
            ("email-job",),
            ("email-rejection-0",),
            ("email-rejection-1",),
        ]
    first_embedding_calls = len(provider.embedding_inputs)

    second = post_chat(
        client,
        "/chat",
        json={"message": "Show me every rejection email that mentioned experience."},
    )

    assert second.status_code == 200
    assert len(provider.embedding_inputs) == first_embedding_calls


def test_chat_request_validates_blank_ids_and_openapi_has_incremental_contract(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    provider = FakeChatProvider()
    client = create_chat_client(database_path, provider)

    invalid = client.post(
        "/chat",
        json={"conversation_id": "   ", "message": "How many applications?"},
    )
    schema = client.get("/openapi.json").json()

    assert invalid.status_code == 422
    operation = schema["paths"]["/chat"]["post"]
    assert "text/event-stream" in operation["responses"]["200"]["content"]
    assert schema["components"]["schemas"]["ChatStreamEvent"]["required"] == [
        "type",
        "conversation_id",
    ]


def test_wipe_removes_persisted_chat_and_embeddings(tmp_path: Path) -> None:
    data_dir = tmp_path / ".jobtracker"
    database_path = migrated_database(data_dir)
    seed_chat_sources(database_path)
    provider = FakeChatProvider()
    with create_chat_client(database_path, provider) as client:
        response = post_chat(
            client,
            "/chat",
            json={"conversation_id": "wipe-me", "message": "What exactly did Acme say?"},
        )
        assert response.status_code == 200
        assert client.get("/chat/history").json()["messages"]

    settings = AppSettings(
        _env_file=None,
        data_dir=data_dir,
        database_url=f"sqlite:///{database_path}",
        fernet_key_file=data_dir / "fernet.key",
    )
    result = asyncio.run(
        wipe_local_data(settings, secret_store=EmptySecretStore(), connection_secret_refs=[])
    )

    assert result.status == "wiped"
    assert not database_path.exists()
    assert not data_dir.exists()


def create_chat_client(
    database_path: Path,
    provider: FakeChatProvider,
    *,
    index_batch_size: int = 1000,
) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite:///{database_path}",
        chat_index_max_emails=index_batch_size,
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


@dataclass(frozen=True)
class ChatStreamTestResponse:
    response: Any
    events: list[dict[str, Any]]

    @property
    def status_code(self) -> int:
        return cast(int, self.response.status_code)

    def json(self) -> dict[str, Any]:
        complete = next(event for event in self.events if event["type"] == "complete")
        return cast(dict[str, Any], complete["response"])


def post_chat(
    client: TestClient,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> ChatStreamTestResponse:
    request_body = payload if payload is not None else json
    assert request_body is not None
    response = client.post(path, json=request_body)
    events = []
    for frame in response.text.split("\n\n"):
        data = next((line[6:] for line in frame.splitlines() if line.startswith("data: ")), None)
        if data is not None:
            events.append(jsonlib.loads(data))
    assert response.headers["content-type"].startswith("text/event-stream")
    return ChatStreamTestResponse(response=response, events=events)


def migrated_database(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def seed_chat_sources(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(
            connection,
            email_id="email-job",
            subject="Interview update",
            body="Acme recruiter: Technical interview moved to Friday.",
            retention="retained",
        )
        insert_raw_email(
            connection,
            email_id="email-non-job",
            subject="Receipt",
            body="private shopping receipt",
            retention="retained",
        )
        insert_raw_email(
            connection,
            email_id="email-debug",
            subject="Debug",
            body="debug-only body",
            retention="debugging",
        )
        insert_raw_email(
            connection,
            email_id="email-metadata",
            subject="Metadata only",
            body=None,
            retention="metadata_only",
        )
        insert_classification(connection, "email-job", is_job_related=True)
        insert_classification(connection, "email-non-job", is_job_related=False)
        insert_classification(connection, "email-debug", is_job_related=True)
        insert_classification(connection, "email-metadata", is_job_related=True)
        ApplicationRepository(connection).upsert_application(
            id="app-acme",
            company="Acme",
            role_title="Platform Engineer",
            source="company_site",
            first_seen_at="2026-06-01T10:00:00+00:00",
            current_status="in_review",
            salary_min=None,
            salary_max=None,
            currency=None,
            location="Remote",
            work_mode="remote",
            seniority="senior",
            sponsorship="unknown",
            tech_stack=["Python"],
            last_activity_at="2026-06-05T10:00:00+00:00",
            created_at="2026-06-01T10:00:00+00:00",
            updated_at="2026-06-05T10:00:00+00:00",
        )
        connection.execute(
            """
            INSERT INTO application_events (
                id, application_id, email_id, event_type, event_at, extract_note
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "event-acme",
                "app-acme",
                "email-job",
                "response",
                "2026-06-05T10:00:00+00:00",
                "Recruiter response",
            ),
        )
        connection.commit()


def insert_raw_email(
    connection: sqlite3.Connection,
    *,
    email_id: str,
    subject: str,
    body: str | None,
    retention: str,
    sent_at: str = "2026-06-05T10:00:00+00:00",
    thread_id: str | None = None,
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
            thread_id or f"thread-{email_id}",
            "recruiter@example.test",
            "candidate@example.test",
            subject,
            sent_at,
            body,
            retention,
            "[]",
            "gmail",
            "2026-06-05T10:01:00+00:00",
        ),
    )


def insert_classification(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    is_job_related: bool,
    category: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO email_classifications (
            email_id, is_job_related, category, confidence, model, prompt_version, classified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            is_job_related,
            category or ("recruiter_outreach" if is_job_related else "other"),
            0.95,
            "fixture-model",
            "v1",
            "2026-06-05T10:02:00+00:00",
        ),
    )


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    company: str,
    source: str = "company_site",
    work_mode: str = "remote",
    sponsorship: str = "unknown",
    current_status: str = "in_review",
    salary_min: int | None = None,
    salary_max: int | None = None,
    role_title: str = "Platform Engineer",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=company,
        role_title=role_title,
        source=source,
        first_seen_at="2026-06-01T10:00:00+00:00",
        current_status=current_status,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=None,
        location="Remote",
        work_mode=work_mode,
        seniority="senior",
        sponsorship=sponsorship,
        tech_stack=["Python"],
        last_activity_at="2026-06-05T10:00:00+00:00",
        created_at="2026-06-01T10:00:00+00:00",
        updated_at="2026-06-05T10:00:00+00:00",
    )


def _embedding_for_text(text: str) -> tuple[float, ...]:
    normalized = text.casefold()
    if "acme" in normalized or "friday" in normalized:
        return (1.0, 0.0)
    return (0.0, 1.0)
