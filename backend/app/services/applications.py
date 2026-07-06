from __future__ import annotations

from datetime import UTC, datetime

from app.db.repositories import ApplicationRepository, EventRepository
from app.models import ApplicationEventRecord, ApplicationRecord
from app.models.records import ApplicationSource, ApplicationStatus, SponsorshipStatus, WorkMode


class ApplicationNotFoundError(LookupError):
    """Raised when an application detail read has no matching source row."""


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
        return self._application_repository.list_applications(
            current_status=status,
            source=source,
            sponsorship=sponsorship,
            first_seen_from=_datetime_filter_value(first_seen_from),
            first_seen_to=_datetime_filter_value(first_seen_to),
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


def _datetime_filter_value(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(UTC).isoformat()
