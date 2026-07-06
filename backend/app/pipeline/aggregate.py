from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.services.normalization import normalize_company_name, normalize_role_title

DEFAULT_APPLICATION_GROUPING_WINDOW_DAYS = 30

_APPLICATION_UUID_NAMESPACE = UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
_EVENT_UUID_NAMESPACE = UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")


class ApplicationGroupingKey(BaseModel):
    """Deterministic application identity signals used by aggregation.

    Thread IDs are opaque provider-owned values. When a thread signal is present,
    aggregation uses it instead of a date window; otherwise the key falls back to
    a UTC date-window bucket.
    """

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
    """Build a deterministic key from normalized application identity signals."""

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


def make_application_id(key: ApplicationGroupingKey) -> str:
    """Generate a deterministic application ID from a grouping key.

    The same grouping key always produces the same UUID,
    which makes re-running aggregation idempotent.
    """

    canonical = json.dumps(
        {
            "company": key.normalized_company,
            "role": key.normalized_role,
            "thread_id": key.thread_id,
            "time_window_start": key.time_window_start.isoformat()
            if key.time_window_start is not None
            else None,
            "window_days": key.time_window_days,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(_APPLICATION_UUID_NAMESPACE, canonical).hex


def make_event_id(
    application_id: str,
    email_id: str | None,
    event_type: str,
    event_at: str,
) -> str:
    """Generate a deterministic event ID from event identity signals.

    Evidence-backed events use (application_id, email_id, event_type, event_at).
    Ghost-inferred events exclude the None email_id but include the other three.
    """

    canonical = json.dumps(
        {
            "application_id": application_id,
            "email_id": email_id,
            "event_type": event_type,
            "event_at": event_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(_EVENT_UUID_NAMESPACE, canonical).hex


__all__ = [
    "ApplicationGroupingKey",
    "DEFAULT_APPLICATION_GROUPING_WINDOW_DAYS",
    "build_application_grouping_key",
    "make_application_id",
    "make_event_id",
]
