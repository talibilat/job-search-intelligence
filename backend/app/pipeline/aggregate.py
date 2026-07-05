from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.normalization import normalize_company_name, normalize_role_title

DEFAULT_APPLICATION_GROUPING_WINDOW_DAYS = 30


class ApplicationGroupingKey(BaseModel):
    """Deterministic application identity signals used by aggregation."""

    model_config = ConfigDict(frozen=True)

    normalized_company: str | None
    normalized_role: str | None
    thread_id: str | None
    time_window_start: date | None
    time_window_days: int = Field(gt=0)

    def as_tuple(self) -> tuple[str | None, str | None, str | None, str | None, int]:
        """Return a stable primitive key for dictionaries, sets, and tests."""

        return (
            self.normalized_company,
            self.normalized_role,
            self.thread_id,
            self.time_window_start.isoformat() if self.time_window_start is not None else None,
            self.time_window_days,
        )


def build_application_grouping_key(
    *,
    company: str | None,
    role_title: str | None,
    thread_id: str | None,
    occurred_at: datetime | None,
    window_days: int = DEFAULT_APPLICATION_GROUPING_WINDOW_DAYS,
) -> ApplicationGroupingKey:
    """Combine extracted application fields into a deterministic grouping key."""

    if window_days <= 0:
        msg = "window_days must be positive"
        raise ValueError(msg)

    normalized_company = normalize_company_name(company) if company is not None else ""
    normalized_role = normalize_role_title(role_title)

    normalized_thread_id = _normalize_thread_id(thread_id)

    return ApplicationGroupingKey(
        normalized_company=normalized_company or None,
        normalized_role=normalized_role,
        thread_id=normalized_thread_id,
        time_window_start=None
        if normalized_thread_id is not None
        else _time_window_start(occurred_at, window_days),
        time_window_days=window_days,
    )


def _normalize_thread_id(thread_id: str | None) -> str | None:
    if thread_id is None:
        return None

    stripped_thread_id = thread_id.strip()
    return stripped_thread_id or None


def _time_window_start(occurred_at: datetime | None, window_days: int) -> date | None:
    if occurred_at is None:
        return None

    occurred_on = _utc_date(occurred_at)
    window_start_ordinal = max(
        1,
        (occurred_on.toordinal() // window_days) * window_days,
    )
    return date.fromordinal(window_start_ordinal)


def _utc_date(value: datetime) -> date:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.date()

    return value.astimezone(UTC).date()


__all__ = [
    "ApplicationGroupingKey",
    "DEFAULT_APPLICATION_GROUPING_WINDOW_DAYS",
    "build_application_grouping_key",
]
