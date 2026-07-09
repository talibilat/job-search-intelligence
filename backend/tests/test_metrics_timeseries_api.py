from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import ApplicationRepository
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_metrics_timeseries_returns_application_counts_by_day(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-1",
            first_seen_at="2026-07-01T09:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-2",
            first_seen_at="2026-07-01T12:00:00+00:00",
        )
        insert_application(
            connection,
            application_id="app-3",
            first_seen_at="2026-07-02T09:00:00+00:00",
        )

    response = create_test_client(database_path).get("/metrics/timeseries")

    assert response.status_code == 200
    assert response.json() == {
        "points": [
            {"period_start": "2026-07-01", "application_count": 2},
            {"period_start": "2026-07-02", "application_count": 1},
        ]
    }


def test_metrics_timeseries_applies_application_filters(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(
            connection,
            application_id="app-linkedin-1",
            first_seen_at="2026-07-01T09:00:00+00:00",
            source="linkedin",
        )
        insert_application(
            connection,
            application_id="app-linkedin-2",
            first_seen_at="2026-07-08T09:00:00+00:00",
            source="linkedin",
        )
        insert_application(
            connection,
            application_id="app-company-site",
            first_seen_at="2026-07-08T10:00:00+00:00",
            source="company_site",
        )

    response = create_test_client(database_path).get(
        "/metrics/timeseries?source=linkedin",
    )

    assert response.status_code == 200
    assert response.json() == {
        "points": [
            {"period_start": "2026-07-01", "application_count": 1},
            {"period_start": "2026-07-08", "application_count": 1},
        ]
    }


def test_metrics_timeseries_endpoint_is_documented_in_openapi() -> None:
    response = TestClient(create_app()).get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/metrics/timeseries"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"] == "#/components/schemas/MetricsTimeseriesResponse"


def create_test_client(database_path: Path) -> TestClient:
    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
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


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    first_seen_at: str,
    source: str = "linkedin",
) -> None:
    ApplicationRepository(connection).upsert_application(
        id=application_id,
        company=f"{application_id} Corp",
        role_title="Software Engineer",
        source=source,
        first_seen_at=first_seen_at,
        current_status="applied",
        last_activity_at=first_seen_at,
        created_at=first_seen_at,
        updated_at=first_seen_at,
        sponsorship="unknown",
        tech_stack=[],
    )
    connection.commit()
