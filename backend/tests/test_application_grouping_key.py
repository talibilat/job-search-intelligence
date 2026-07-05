from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.pipeline.aggregate import build_application_grouping_key


def test_application_grouping_key_combines_normalized_company_role_thread_and_window() -> None:
    first_key = build_application_grouping_key(
        company="OpenAI, Inc.",
        role_title="Senior SWE II - Backend (Remote)",
        thread_id=" thread-123 ",
        occurred_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )
    second_key = build_application_grouping_key(
        company="openai.com",
        role_title="Software Engineer, Backend",
        thread_id="thread-123",
        occurred_at=datetime(2026, 7, 6, 9, 0, tzinfo=UTC),
    )

    assert first_key == second_key
    assert first_key.normalized_company == "openai"
    assert first_key.normalized_role == "back end software engineer"
    assert first_key.thread_id == "thread-123"
    assert first_key.time_window_start is not None
    assert first_key.time_window_start.isoformat() == "2026-07-03"
    assert first_key.time_window_days == 30
    assert first_key.as_tuple() == (
        "openai",
        "back end software engineer",
        "thread-123",
        "2026-07-03",
        30,
    )


def test_application_grouping_key_preserves_distinct_thread_and_time_signals() -> None:
    base_key = build_application_grouping_key(
        company="Example Corp",
        role_title="Data Scientist III",
        thread_id="thread-a",
        occurred_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )

    different_thread_key = build_application_grouping_key(
        company="Example Corporation",
        role_title="Data Scientist",
        thread_id="thread-b",
        occurred_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )
    different_window_key = build_application_grouping_key(
        company="Example Corporation",
        role_title="Data Scientist",
        thread_id="thread-a",
        occurred_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )

    assert different_thread_key != base_key
    assert different_window_key != base_key
    assert different_window_key.time_window_start is not None
    assert different_window_key.time_window_start.isoformat() == "2026-08-02"


def test_application_grouping_key_uses_utc_date_for_time_window() -> None:
    pacific = timezone(timedelta(hours=-7))

    key = build_application_grouping_key(
        company="Acme LLC",
        role_title="ML Engineer",
        thread_id=None,
        occurred_at=datetime(2026, 7, 5, 23, 30, tzinfo=pacific),
        window_days=7,
    )

    assert key.normalized_company == "acme"
    assert key.normalized_role == "machine learning engineer"
    assert key.thread_id is None
    assert key.time_window_start is not None
    assert key.time_window_start.isoformat() == "2026-07-05"
    assert key.as_tuple() == (
        "acme",
        "machine learning engineer",
        None,
        "2026-07-05",
        7,
    )


def test_application_grouping_key_keeps_missing_signals_explicit() -> None:
    key = build_application_grouping_key(
        company="   ",
        role_title="---",
        thread_id="   ",
        occurred_at=None,
    )

    assert key.normalized_company is None
    assert key.normalized_role is None
    assert key.thread_id is None
    assert key.time_window_start is None
    assert key.as_tuple() == (None, None, None, None, 30)


def test_application_grouping_key_rejects_non_positive_window_days() -> None:
    with pytest.raises(ValueError, match="window_days must be positive"):
        build_application_grouping_key(
            company="Example Corp",
            role_title="Software Engineer",
            thread_id="thread-1",
            occurred_at=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
            window_days=0,
        )
