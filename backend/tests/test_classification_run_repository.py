from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from app import models
from app.db import repositories

BACKEND_ROOT = Path(__file__).resolve().parents[1]
STARTED_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 7, 5, 12, 2, tzinfo=UTC)


def test_upsert_run_records_per_run_tokens_and_estimated_cost(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = repositories.ClassificationRunRepository(connection)
    first_run = classification_run(classified_count=1, total_tokens=80)
    completed_run = classification_run(
        classified_count=2,
        prompt_tokens=120,
        completion_tokens=30,
        total_tokens=150,
        estimated_cost_usd=Decimal("0.000450"),
    )

    repository.upsert_run(first_run)
    repository.upsert_run(completed_run)

    stored = repository.fetch_run("classification-run-1")
    count_row = connection.execute("SELECT COUNT(*) FROM classification_runs").fetchone()
    assert stored == completed_run
    assert count_row is not None
    assert tuple(count_row) == (1,)


def test_fetch_run_returns_none_for_unknown_run(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = repositories.ClassificationRunRepository(connection)

    assert repository.fetch_run("missing-run") is None


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def classification_run(
    *,
    classified_count: int,
    prompt_tokens: int = 64,
    completion_tokens: int = 16,
    total_tokens: int,
    estimated_cost_usd: Decimal = Decimal("0.000240"),
) -> models.ClassificationRunRecord:
    return models.ClassificationRunRecord(
        id="classification-run-1",
        provider="azure_openai",
        model="gpt-4.1-mini",
        prompt_version="prompt-v1",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        candidate_count=2,
        classified_count=classified_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
