from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)
APPLIED_AT = "2026-07-01T09:00:00+00:00"


def test_post_application_reset_lock_clears_lock_with_audit(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-1", manual_lock=True)

    response = create_test_client(database_path).post(
        "/applications/app-1/reset-lock",
        json={"reason": "Let aggregation manage this application again."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["application"]["id"] == "app-1"
    assert body["application"]["manual_lock"] is False
    assert body["correction"]["application_id"] == "app-1"
    assert body["correction"]["correction_type"] == "reset_lock"
    assert body["correction"]["reason"] == "Let aggregation manage this application again."


def test_post_application_reset_lock_returns_typed_not_found_error(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)

    response = create_test_client(database_path).post(
        "/applications/missing-app/reset-lock",
        json={},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Application was not found.",
            "details": [],
        }
    }


def test_post_application_reset_lock_rejects_unlocked_application(
    tmp_path: Path,
) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        insert_application(connection, application_id="app-1", manual_lock=False)

    response = create_test_client(database_path).post(
        "/applications/app-1/reset-lock",
        json={"reason": "No lock is active."},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "Application is not manually locked.",
            "details": [],
        }
    }


def test_application_reset_lock_openapi_documents_typed_errors() -> None:
    responses = app_openapi_paths()["/applications/{application_id}/reset-lock"]["post"][
        "responses"
    ]

    assert responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }


def create_test_client(database_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    return TestClient(app)


def app_openapi_paths() -> dict[str, dict[str, Any]]:
    return cast(dict[str, dict[str, Any]], create_app().openapi()["paths"])


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
    manual_lock: bool,
) -> None:
    connection.execute(
        """
        INSERT INTO applications (
            id, company, role_title, source, first_seen_at,
            current_status, salary_min, salary_max, currency,
            location, work_mode, seniority, sponsorship,
            tech_stack, last_activity_at, manual_lock,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            "Acme Corp",
            "Software Engineer",
            "other",
            APPLIED_AT,
            "withdrawn" if manual_lock else "applied",
            None,
            None,
            None,
            None,
            None,
            None,
            "unknown",
            json.dumps([]),
            APPLIED_AT,
            int(manual_lock),
            APPLIED_AT,
            APPLIED_AT,
        ),
    )
