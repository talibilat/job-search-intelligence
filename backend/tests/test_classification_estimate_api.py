from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.config import AppSettings, ClassificationMode, LLMProviderName, get_settings
from app.main import create_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_get_classification_estimate_counts_candidates_tokens_and_cost(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "needs-classification", body_text="a" * 32)
        insert_raw_email(connection, "stale-classification", body_text="b" * 16)
        insert_raw_email(connection, "stale-model", body_text="d" * 8)
        insert_raw_email(
            connection,
            "debugging-retention",
            body_text="debugging body",
            body_retention_state="debugging",
        )
        insert_raw_email(connection, "current-classification", body_text="c" * 80)
        insert_raw_email(
            connection,
            "metadata-only",
            body_text=None,
            body_retention_state="metadata_only",
        )
        insert_classification(connection, "stale-classification", prompt_version="v1")
        insert_classification(
            connection,
            "stale-model",
            prompt_version="v2",
            model="previous-model",
        )
        insert_classification(connection, "current-classification", prompt_version="v2")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        classification_mode=ClassificationMode.HYBRID,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        azure_openai_chat_deployment="gpt-4o-mini",
        classification_prompt_version="v2",
        classification_estimate_chars_per_unit=4,
        classification_estimate_prompt_overhead_units=20,
        classification_estimate_completion_units_per_candidate=6,
        classification_input_cost_per_1k_units_usd=1.0,
        classification_output_cost_per_1k_units_usd=2.0,
    )
    client = TestClient(app)

    response = client.get("/classification/estimate")

    assert response.status_code == 200
    assert response.json() == {
        "candidate_count": 3,
        "estimated_prompt_tokens": 74,
        "estimated_completion_tokens": 18,
        "estimated_total_tokens": 92,
        "estimated_cost_usd": pytest.approx(0.11),
        "currency": "USD",
        "cost_estimate_available": True,
        "classification_mode": "hybrid",
        "llm_provider": "azure_openai",
        "model": "gpt-4o-mini",
        "prompt_version": "v2",
        "token_estimate_method": (
            "ceil(body_text_chars / 4) + 20 prompt overhead tokens per candidate; "
            "6 completion tokens per candidate"
        ),
    }


def test_get_classification_estimate_reports_zero_cost_for_local_mode(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    create_classification_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        insert_raw_email(connection, "local-candidate", body_text="local body")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        classification_mode=ClassificationMode.LOCAL,
        llm_provider=LLMProviderName.OLLAMA,
        ollama_chat_model="llama3.1",
    )
    client = TestClient(app)

    response = client.get("/classification/estimate")

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 1
    assert response.json()["estimated_cost_usd"] == 0.0
    assert response.json()["cost_estimate_available"] is True
    assert response.json()["model"] == "llama3.1"


def test_get_classification_estimate_does_not_create_missing_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing" / "jobtracker.sqlite3"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(app)

    response = client.get("/classification/estimate")

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 0
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
