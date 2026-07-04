from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.repositories import SyntheticFixtureRepository


def test_synthetic_fixture_loader_loads_json_file_into_core_tables() -> None:
    connection = sqlite3.connect(":memory:")
    repository = SyntheticFixtureRepository(connection)

    result = repository.load_file(sample_fixture_path())

    assert result.fixture_id == "basic-job-search"
    assert result.email_count == 2
    assert result.classification_count == 2
    assert result.application_count == 1
    assert result.event_count == 2
    assert count_rows(connection, "raw_emails") == 2
    assert count_rows(connection, "email_classifications") == 2
    assert count_rows(connection, "applications") == 1
    assert count_rows(connection, "application_events") == 2

    application = connection.execute(
        "SELECT id, company, current_status, tech_stack FROM applications"
    ).fetchone()
    assert tuple(application) == (
        "application-example-systems-backend-engineer",
        "Example Systems",
        "rejected",
        '["Python","FastAPI"]',
    )

    event_application_ids = connection.execute(
        "SELECT DISTINCT application_id FROM application_events"
    ).fetchall()
    assert [tuple(row) for row in event_application_ids] == [
        ("application-example-systems-backend-engineer",)
    ]


def test_synthetic_fixture_loader_is_idempotent_for_same_fixture() -> None:
    connection = sqlite3.connect(":memory:")
    repository = SyntheticFixtureRepository(connection)

    first_result = repository.load_file(sample_fixture_path())
    second_result = repository.load_file(sample_fixture_path())

    assert second_result == first_result
    assert count_rows(connection, "raw_emails") == 2
    assert count_rows(connection, "email_classifications") == 2
    assert count_rows(connection, "applications") == 1
    assert count_rows(connection, "application_events") == 2


def sample_fixture_path() -> Path:
    backend_root = Path(__file__).resolve().parents[1]
    return backend_root / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    assert row is not None
    return int(row[0])
