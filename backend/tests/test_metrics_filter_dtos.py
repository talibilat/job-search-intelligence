from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.models import MetricsFilter
from pydantic import ValidationError


def test_metrics_filter_accepts_dashboard_filter_fields() -> None:
    filter_dto = MetricsFilter(
        status="interview",
        source="linkedin",
        sponsorship="offered",
        first_seen_from=datetime(2026, 7, 1, 9, 0, tzinfo=timezone(timedelta(hours=-4))),
        first_seen_to=datetime(2026, 7, 31, 23, 59, tzinfo=UTC),
        role="  Backend Engineer  ",
        salary_min=120000,
        salary_max=180000,
        work_mode="remote",
    )

    assert filter_dto.status == "interview"
    assert filter_dto.source == "linkedin"
    assert filter_dto.sponsorship == "offered"
    assert filter_dto.first_seen_from == datetime(2026, 7, 1, 13, 0, tzinfo=UTC)
    assert filter_dto.first_seen_to == datetime(2026, 7, 31, 23, 59, tzinfo=UTC)
    assert filter_dto.role == "Backend Engineer"
    assert filter_dto.salary_min == 120000
    assert filter_dto.salary_max == 180000
    assert filter_dto.work_mode == "remote"


def test_metrics_filter_rejects_inverted_salary_band() -> None:
    with pytest.raises(
        ValidationError,
        match="salary_min must be less than or equal to salary_max",
    ):
        MetricsFilter(salary_min=200000, salary_max=100000)


def test_metrics_filter_rejects_inverted_first_seen_range_after_utc_normalization() -> None:
    with pytest.raises(
        ValidationError,
        match="first_seen_from must be less than or equal to first_seen_to",
    ):
        MetricsFilter(
            first_seen_from=datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
            first_seen_to=datetime(2026, 7, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))),
        )


@pytest.mark.parametrize("field", ["first_seen_from", "first_seen_to"])
def test_metrics_filter_rejects_naive_datetimes(field: str) -> None:
    with pytest.raises(ValidationError, match=f"{field} must include a timezone offset"):
        MetricsFilter.model_validate({field: datetime(2026, 7, 1, 9, 0)})


def test_metrics_filter_rejects_blank_role() -> None:
    with pytest.raises(ValidationError, match="role must not be blank"):
        MetricsFilter(role="   ")
