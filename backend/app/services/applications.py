from __future__ import annotations

from app.db.repositories import ApplicationRepository
from app.models import ApplicationRecord


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
