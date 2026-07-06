from __future__ import annotations

from app.db.repositories import ApplicationRepository, EventRepository
from app.models import ApplicationEventRecord, ApplicationRecord


class ApplicationNotFoundError(LookupError):
    """Raised when an application detail read has no matching source row."""


class ApplicationDetailService:
    def __init__(self, application_repository: ApplicationRepository) -> None:
        self._application_repository = application_repository

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
