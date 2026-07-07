from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import ApplicationRepository, InsightRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)


def test_save_generated_insight_persists_and_fetches_exact_cache_hit(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = InsightRepository(connection)

    record = repository.save_generated_insight(
        insight_type="why_rejected",
        content="Rejected applications repeatedly mention missing systems experience.",
        inputs_hash="facts-hash-v1",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT,
    )

    cached = repository.get_cached_insight(
        insight_type="why_rejected",
        inputs_hash="facts-hash-v1",
        model="gpt-4.1-mini",
    )
    wrong_hash = repository.get_cached_insight(
        insight_type="why_rejected",
        inputs_hash="facts-hash-v2",
        model="gpt-4.1-mini",
    )

    assert record.id > 0
    assert record.type == "why_rejected"
    assert record.content == "Rejected applications repeatedly mention missing systems experience."
    assert record.inputs_hash == "facts-hash-v1"
    assert record.model == "gpt-4.1-mini"
    assert record.generated_at == GENERATED_AT
    assert record.is_stale is False
    assert cached == record
    assert wrong_hash is None


def test_save_generated_insight_accepts_recurring_feedback_type(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = InsightRepository(connection)

    record = repository.save_generated_insight(
        insight_type="recurring_feedback",
        content="Feedback repeatedly recommends deeper system design examples.",
        inputs_hash="feedback-hash-v1",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT,
    )

    cached = repository.get_cached_insight(
        insight_type="recurring_feedback",
        inputs_hash="feedback-hash-v1",
        model="gpt-4.1-mini",
    )

    assert record.type == "recurring_feedback"
    assert cached == record


def test_save_generated_insight_replaces_existing_type_cache(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = InsightRepository(connection)
    first = repository.save_generated_insight(
        insight_type="story",
        content="Your search is weighted toward backend roles.",
        inputs_hash="facts-hash-v1",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT,
    )

    second = repository.save_generated_insight(
        insight_type="story",
        content="Your search is shifting toward platform roles.",
        inputs_hash="facts-hash-v2",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT + timedelta(hours=1),
    )

    rows = repository.fetch_all("SELECT * FROM insights ORDER BY id")
    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0] == second
    assert rows[0].content == "Your search is shifting toward platform roles."
    assert rows[0].inputs_hash == "facts-hash-v2"


def test_save_generated_insight_accepts_strongest_weakest_signals_type(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    repository = InsightRepository(connection)

    record = repository.save_generated_insight(
        insight_type="strongest_weakest_signals",
        content="Your strongest signal is backend interviews; your weakest is platform rejections.",
        inputs_hash="facts-hash-signals-v1",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT,
    )

    cached = repository.get_cached_insight(
        insight_type="strongest_weakest_signals",
        inputs_hash="facts-hash-signals-v1",
        model="gpt-4.1-mini",
    )

    assert record.type == "strongest_weakest_signals"
    assert cached == record


def test_strongest_weakest_signals_migration_preserves_staleness_triggers(
    tmp_path: Path,
) -> None:
    connection = migrated_connection(tmp_path)
    repository = InsightRepository(connection)
    record = repository.save_generated_insight(
        insight_type="strongest_weakest_signals",
        content="Your strongest and weakest signals are grounded in the whole history.",
        inputs_hash="facts-hash-signals-v1",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT,
    )

    ApplicationRepository(connection).upsert_application(
        id="application-after-insight",
        company="Acme Corp",
        role_title="Backend Engineer",
        source="linkedin",
        first_seen_at="2026-07-01T09:00:00+00:00",
        current_status="applied",
        last_activity_at="2026-07-01T09:00:00+00:00",
        created_at="2026-07-01T09:00:00+00:00",
        updated_at="2026-07-01T09:00:00+00:00",
    )

    updated = repository.fetch_insight(record.id)

    assert updated is not None
    assert updated.is_stale is True


def test_mark_stale_except_inputs_hash_invalidates_changed_inputs(tmp_path: Path) -> None:
    connection = migrated_connection(tmp_path)
    repository = InsightRepository(connection)
    old = repository.save_generated_insight(
        insight_type="skill_gaps",
        content="Older skill gap summary.",
        inputs_hash="facts-hash-v1",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT,
    )
    current = repository.save_generated_insight(
        insight_type="weekly_actions",
        content="Apply to three platform roles next week.",
        inputs_hash="facts-hash-v2",
        model="gpt-4.1-mini",
        generated_at=GENERATED_AT + timedelta(hours=1),
    )

    stale_count = repository.mark_stale_except_inputs_hash("facts-hash-v2")

    stale_record = repository.fetch_insight(old.id)
    current_record = repository.fetch_insight(current.id)
    assert stale_count == 1
    assert stale_record is not None
    assert stale_record.is_stale is True
    assert current_record is not None
    assert current_record.is_stale is False
    assert (
        repository.get_cached_insight(
            insight_type="skill_gaps",
            inputs_hash="facts-hash-v1",
            model="gpt-4.1-mini",
        )
        is None
    )


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)
