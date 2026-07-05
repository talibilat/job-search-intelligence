from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.config import AppSettings, ClassificationMode, LLMProviderName, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_get_classification_reprocessing_plan_partitions_target_version_candidates(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "unclassified", body_text="needs first classification")
        insert_raw_email(connection, "stale-model", body_text="model changed")
        insert_raw_email(connection, "stale-prompt", body_text="prompt changed")
        insert_raw_email(connection, "up-to-date", body_text="already current")
        insert_raw_email(
            connection,
            "debugging-retention",
            body_text="debugging body",
            body_retention_state="debugging",
        )
        insert_raw_email(
            connection,
            "metadata-only",
            body_text=None,
            body_retention_state="metadata_only",
        )
        insert_classification(
            connection,
            "stale-model",
            model="previous-model",
            prompt_version="v1",
        )
        insert_classification(connection, "stale-prompt", prompt_version="v1")
        insert_classification(connection, "up-to-date", prompt_version="v2")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        classification_mode=ClassificationMode.HYBRID,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        azure_openai_chat_deployment="gpt-4o-mini",
        classification_prompt_version="v2",
    )
    client = TestClient(app)

    response = client.get("/classification/reprocessing-plan")

    assert response.status_code == 200
    assert response.json() == {
        "email_provider": "gmail",
        "classification_mode": "hybrid",
        "llm_provider": "azure_openai",
        "target_model": "gpt-4o-mini",
        "target_prompt_version": "v2",
        "retained_candidate_count": 4,
        "up_to_date_count": 1,
        "unclassified_count": 1,
        "stale_model_count": 1,
        "stale_prompt_version_count": 1,
        "reprocess_count": 3,
        "should_reprocess": True,
        "selection_policy": (
            "Reprocess retained candidate emails with no classification, a stored model "
            "different from the target model, or a stored prompt_version different from "
            "the target prompt version."
        ),
    }


def test_get_classification_reprocessing_plan_marks_current_rows_unchanged(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "up-to-date", body_text="already current")
        insert_classification(connection, "up-to-date", prompt_version="v2")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        llm_provider=LLMProviderName.AZURE_OPENAI,
        azure_openai_chat_deployment="gpt-4o-mini",
        classification_prompt_version="v2",
    )
    client = TestClient(app)

    response = client.get("/classification/reprocessing-plan")

    assert response.status_code == 200
    assert response.json()["retained_candidate_count"] == 1
    assert response.json()["up_to_date_count"] == 1
    assert response.json()["reprocess_count"] == 0
    assert response.json()["should_reprocess"] is False


def test_get_classification_reprocessing_plan_does_not_create_missing_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing" / "jobtracker.sqlite3"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get("/classification/reprocessing-plan")

    assert response.status_code == 200
    assert response.json()["retained_candidate_count"] == 0
    assert response.json()["reprocess_count"] == 0
    assert response.json()["should_reprocess"] is False
    assert not database_path.exists()
    assert not database_path.parent.exists()


def create_classification_tables(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE raw_emails (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                from_addr TEXT,
                to_addr TEXT,
                subject TEXT,
                sent_at TEXT,
                body_text TEXT,
                body_retention_state TEXT NOT NULL,
                labels TEXT NOT NULL,
                provider TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE email_classifications (
                email_id TEXT PRIMARY KEY,
                is_job_related INTEGER NOT NULL,
                category TEXT NOT NULL,
                confidence REAL NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                classified_at TEXT NOT NULL
            )
            """,
        )


def insert_raw_email(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    body_text: str | None,
    body_retention_state: str = "retained",
) -> None:
    connection.execute(
        """
        INSERT INTO raw_emails (
            id,
            thread_id,
            from_addr,
            to_addr,
            subject,
            sent_at,
            body_text,
            body_retention_state,
            labels,
            provider,
            ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            f"thread-{email_id}",
            "jobs@example.test",
            "me@example.test",
            "Application update",
            NOW.isoformat(),
            body_text,
            body_retention_state,
            "[]",
            "gmail",
            NOW.isoformat(),
        ),
    )


def insert_classification(
    connection: sqlite3.Connection,
    email_id: str,
    *,
    prompt_version: str,
    model: str = "gpt-4o-mini",
) -> None:
    connection.execute(
        """
        INSERT INTO email_classifications (
            email_id,
            is_job_related,
            category,
            confidence,
            model,
            prompt_version,
            classified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            1,
            "application_confirmation",
            0.98,
            model,
            prompt_version,
            NOW.isoformat(),
        ),
    )
