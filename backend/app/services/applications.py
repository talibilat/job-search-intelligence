from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

from app.db.repositories import (
    ApplicationRepository,
    CorrectionConflictRepository,
    CorrectionRepository,
    EventRepository,
)
from app.models import (
    ApplicationCorrectionConflictRecord,
    ApplicationCorrectionRecord,
    ApplicationEventRecord,
    ApplicationRecord,
)
from app.models.application import ApplicationStatusCountsResponse
from app.models.records import (
    ApplicationEventTimelineRecord,
    ApplicationSource,
    ApplicationStatus,
    RecentApplicationEventRecord,
    SponsorshipStatus,
    WorkMode,
)


class ApplicationNotFoundError(LookupError):
    """Raised when an application detail read has no matching source row."""


class ApplicationFilterValidationError(ValueError):
    def __init__(self, *, field: str, message: str, error_type: str) -> None:
        self.field = field
        self.message = message
        self.error_type = error_type
        super().__init__(message)


class ApplicationDetailService:
    def __init__(self, application_repository: ApplicationRepository) -> None:
        self._application_repository = application_repository

    def list_applications(
        self,
        *,
        status: ApplicationStatus | None = None,
        source: ApplicationSource | None = None,
        sponsorship: SponsorshipStatus | None = None,
        first_seen_from: datetime | None = None,
        first_seen_to: datetime | None = None,
        role: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        work_mode: WorkMode | None = None,
    ) -> list[ApplicationRecord]:
        _validate_salary_band(salary_min=salary_min, salary_max=salary_max)
        return self._application_repository.list_applications(
            current_status=status,
            source=source,
            sponsorship=sponsorship,
            first_seen_from=_datetime_filter_value(first_seen_from, "first_seen_from"),
            first_seen_to=_datetime_filter_value(first_seen_to, "first_seen_to"),
            role=role,
            salary_min=salary_min,
            salary_max=salary_max,
            work_mode=work_mode,
        )

    def get_application(self, application_id: str) -> ApplicationRecord:
        application = self._application_repository.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(application_id)
        return application

    def get_status_counts(self) -> ApplicationStatusCountsResponse:
        """Return deterministic per-status application counts, with zero-filled statuses."""

        stored_counts = self._application_repository.count_by_status()
        counts: dict[ApplicationStatus, int] = {
            status: stored_counts.get(status, 0) for status in get_args(ApplicationStatus.__value__)
        }
        return ApplicationStatusCountsResponse(
            total=sum(counts.values()),
            counts=counts,
        )


class ApplicationEventsService:
    def __init__(
        self,
        *,
        application_repository: ApplicationRepository,
        event_repository: EventRepository,
    ) -> None:
        self._application_repository = application_repository
        self._event_repository = event_repository

    def list_application_events(self, application_id: str) -> list[ApplicationEventRecord]:
        application = self._application_repository.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(application_id)
        return self._event_repository.list_by_application_id(application_id)

    def list_application_timeline(
        self,
        application_id: str,
    ) -> list[ApplicationEventTimelineRecord]:
        """Return one application's timeline with email subject and confidence metadata."""

        application = self._application_repository.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(application_id)
        return self._event_repository.list_timeline_for_application(application_id)

    def list_recent_events(self, *, limit: int = 10) -> list[RecentApplicationEventRecord]:
        """Return the newest events across all applications for the activity feed."""

        return self._event_repository.list_recent_events(limit=limit)


class ApplicationCorrectionConflictService:
    def __init__(
        self,
        *,
        application_repository: ApplicationRepository,
        conflict_repository: CorrectionConflictRepository,
    ) -> None:
        self._application_repository = application_repository
        self._conflict_repository = conflict_repository

    def list_application_conflicts(
        self,
        application_id: str,
    ) -> list[ApplicationCorrectionConflictRecord]:
        application = self._application_repository.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(application_id)
        return self._conflict_repository.list_by_application_id(application_id)


class ApplicationCorrectionHistoryService:
    def __init__(
        self,
        *,
        application_repository: ApplicationRepository,
        correction_repository: CorrectionRepository,
    ) -> None:
        self._application_repository = application_repository
        self._correction_repository = correction_repository

    def list_application_corrections(
        self,
        application_id: str,
    ) -> list[ApplicationCorrectionRecord]:
        application = self._application_repository.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(application_id)
        return list(reversed(self._correction_repository.list_by_application_id(application_id)))


def _validate_salary_band(*, salary_min: int | None, salary_max: int | None) -> None:
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise ApplicationFilterValidationError(
            field="salary_min",
            message="salary_min must be less than or equal to salary_max.",
            error_type="value_error",
        )


def _datetime_filter_value(value: datetime | None, field: str) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApplicationFilterValidationError(
            field=field,
            message=f"{field} must include a timezone offset.",
            error_type="timezone_aware",
        )
    return value.astimezone(UTC).isoformat()
