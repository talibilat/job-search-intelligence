from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import MetricsRepository, SyntheticFixtureRepository
from app.models.metrics import MetricsFilter
from app.services.diagnostics import DiagnosticsService

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_diagnostics_service_outputs_match_synthetic_fixture(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        load_result = SyntheticFixtureRepository(connection).load_file(diagnostic_fixture_path())
        service = DiagnosticsService(metrics_repository=MetricsRepository(connection))

        diagnostics = service.get_diagnostics(dimensions=("source",))

    assert load_result.fixture_id == "diagnostic-job-search"
    assert load_result.application_count == 5
    assert load_result.event_count == 11
    assert diagnostics.total_applications == 5
    assert diagnostics.baseline_response_count == 3
    assert diagnostics.baseline_response_rate == 0.6
    assert [segment.model_dump() for segment in diagnostics.segments] == [
        {
            "dimension": "source",
            "value": "company_site",
            "application_count": 2,
            "response_count": 2,
            "interview_count": 0,
            "offer_count": 0,
            "success_count": 0,
            "response_rate": 1.0,
            "interview_rate": 0.0,
            "offer_rate": 0.0,
            "success_rate": 0.0,
            "response_rate_lift": 0.4,
            "success_rate_lift": -0.2,
        },
        {
            "dimension": "source",
            "value": "linkedin",
            "application_count": 3,
            "response_count": 1,
            "interview_count": 1,
            "offer_count": 1,
            "success_count": 1,
            "response_rate": 1 / 3,
            "interview_rate": 1 / 3,
            "offer_rate": 1 / 3,
            "success_rate": 1 / 3,
            "response_rate_lift": (1 / 3) - 0.6,
            "success_rate_lift": (1 / 3) - 0.2,
        },
    ]
    assert diagnostics.strongest_response_segments == [diagnostics.segments[0]]
    assert diagnostics.weakest_response_segments == [diagnostics.segments[1]]


def test_diagnostics_fixture_outputs_compose_with_filters(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        SyntheticFixtureRepository(connection).load_file(diagnostic_fixture_path())
        service = DiagnosticsService(metrics_repository=MetricsRepository(connection))

        diagnostics = service.get_diagnostics(
            dimensions=("source",),
            filters=MetricsFilter(source="linkedin"),
        )

    assert diagnostics.total_applications == 3
    assert diagnostics.baseline_response_count == 1
    assert diagnostics.baseline_response_rate == 1 / 3
    assert [segment.model_dump() for segment in diagnostics.segments] == [
        {
            "dimension": "source",
            "value": "linkedin",
            "application_count": 3,
            "response_count": 1,
            "interview_count": 1,
            "offer_count": 1,
            "success_count": 1,
            "response_rate": 1 / 3,
            "interview_rate": 1 / 3,
            "offer_rate": 1 / 3,
            "success_rate": 1 / 3,
            "response_rate_lift": 0.0,
            "success_rate_lift": 0.0,
        },
    ]


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def diagnostic_fixture_path() -> Path:
    return BACKEND_ROOT / "tests" / "fixtures" / "synthetic" / "diagnostic_job_search.json"
