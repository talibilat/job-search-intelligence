from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.models.correction import ApplicationSplitRequest, ApplicationSplitResponse
from app.models.records import (
    ApplicationEventRecord,
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    JsonObject,
)

type Clock = Callable[[], datetime]

_EVENT_STATUS_BY_TYPE: dict[ApplicationEventType, ApplicationStatus] = {
    "applied": "applied",
    "response": "in_review",
    "assessment": "assessment",
    "interview_scheduled": "interview",
    "feedback": "in_review",
    "rejection": "rejected",
    "offer": "offer",
    "ghost_inferred": "ghosted",
}
_STATUS_PRIORITY: tuple[ApplicationStatus, ...] = (
    "offer",
    "rejected",
    "ghosted",
    "interview",
    "assessment",
    "in_review",
    "applied",
)


class ApplicationCorrectionServiceError(Exception):
    def __init__(self, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class ApplicationNotFoundError(ApplicationCorrectionServiceError):
    pass


class ApplicationSplitConflictError(ApplicationCorrectionServiceError):
    pass


class ApplicationCorrectionService:
    """Business logic for audited manual application corrections."""

    def __init__(
        self,
        *,
        application_repository: ApplicationRepository,
        event_repository: EventRepository,
        correction_repository: CorrectionRepository,
        clock: Clock | None = None,
    ) -> None:
        self._application_repository = application_repository
        self._event_repository = event_repository
        self._correction_repository = correction_repository
        self._clock = clock or _utcnow

    def split_application(
        self,
        *,
        application_id: str,
        request: ApplicationSplitRequest,
    ) -> ApplicationSplitResponse:
        self._validate_shared_connection()

        source_before = self._application_repository.get_by_id(application_id)
        if source_before is None:
            raise ApplicationNotFoundError("Application was not found.")

        source_events_before = self._event_repository.list_for_application(application_id)
        selected_events = self._event_repository.list_by_ids_for_application(
            application_id=application_id,
            event_ids=request.event_ids,
        )
        self._validate_split_selection(
            requested_event_ids=request.event_ids,
            source_events=source_events_before,
            selected_events=selected_events,
        )

        selected_event_ids = {event.id for event in selected_events}
        remaining_events = [
            event for event in source_events_before if event.id not in selected_event_ids
        ]
        new_application_id = make_manual_split_application_id(
            source_application_id=application_id,
            event_ids=request.event_ids,
        )
        if self._application_repository.get_by_id(new_application_id) is not None:
            raise ApplicationSplitConflictError("Split target application already exists.")

        now = self._clock()
        now_iso = now.isoformat()
        new_first_seen_at, new_last_activity_at = _event_bounds(selected_events)
        source_first_seen_at, source_last_activity_at = _event_bounds(remaining_events)
        source_current_status = (
            source_before.current_status
            if source_before.manual_lock
            else _derive_current_status(remaining_events)
        )
        source_application_fields = request.source_application or source_before

        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            self._application_repository.upsert_application(
                id=new_application_id,
                company=request.new_application.company,
                role_title=request.new_application.role_title,
                source=request.new_application.source,
                first_seen_at=new_first_seen_at.isoformat(),
                current_status=_derive_current_status(selected_events),
                salary_min=request.new_application.salary_min,
                salary_max=request.new_application.salary_max,
                currency=request.new_application.currency,
                location=request.new_application.location,
                work_mode=request.new_application.work_mode,
                seniority=request.new_application.seniority,
                sponsorship=request.new_application.sponsorship,
                tech_stack=request.new_application.tech_stack,
                last_activity_at=new_last_activity_at.isoformat(),
                created_at=now_iso,
                updated_at=now_iso,
            )
            moved_count = self._event_repository.reassign_events(
                event_ids=request.event_ids,
                from_application_id=application_id,
                to_application_id=new_application_id,
            )
            if moved_count != len(request.event_ids):
                raise ApplicationSplitConflictError(
                    "One or more selected events could not be moved.",
                )

            self._application_repository.update_timeline_summary(
                application_id=application_id,
                first_seen_at=source_first_seen_at.isoformat(),
                current_status=source_current_status,
                company=source_application_fields.company,
                role_title=source_application_fields.role_title,
                source=source_application_fields.source,
                salary_min=source_application_fields.salary_min,
                salary_max=source_application_fields.salary_max,
                currency=source_application_fields.currency,
                location=source_application_fields.location,
                work_mode=source_application_fields.work_mode,
                seniority=source_application_fields.seniority,
                sponsorship=source_application_fields.sponsorship,
                tech_stack=source_application_fields.tech_stack,
                last_activity_at=source_last_activity_at.isoformat(),
                updated_at=now_iso,
            )
            source_after = self._application_repository.get_by_id(application_id)
            new_application = self._application_repository.get_by_id(new_application_id)
            moved_events = self._event_repository.list_by_ids_for_application(
                application_id=new_application_id,
                event_ids=request.event_ids,
            )
            if source_after is None or new_application is None:
                raise ApplicationSplitConflictError("Split application state could not be loaded.")

            correction = self._correction_repository.create_correction(
                application_id=application_id,
                correction_type="split",
                before_json={
                    "source_application": _application_json(source_before),
                    "source_events": _events_json(source_events_before),
                    "requested_event_ids": list(request.event_ids),
                },
                after_json={
                    "source_application": _application_json(source_after),
                    "new_application": _application_json(new_application),
                    "moved_event_ids": list(request.event_ids),
                    "moved_events": _events_json(moved_events),
                },
                reason=request.reason,
                created_at=now_iso,
            )

        if should_commit:
            self._application_repository.connection.commit()

        return ApplicationSplitResponse(
            source_application=source_after,
            new_application=new_application,
            moved_events=moved_events,
            correction=correction,
        )

    @staticmethod
    def _validate_split_selection(
        *,
        requested_event_ids: list[str],
        source_events: list[ApplicationEventRecord],
        selected_events: list[ApplicationEventRecord],
    ) -> None:
        if not source_events:
            raise ApplicationSplitConflictError("Application has no events to split.")

        selected_event_ids = {event.id for event in selected_events}
        missing_event_ids = [
            event_id for event_id in requested_event_ids if event_id not in selected_event_ids
        ]
        if missing_event_ids:
            raise ApplicationSplitConflictError(
                "One or more selected events do not belong to this application.",
            )
        if len(selected_events) == len(source_events):
            raise ApplicationSplitConflictError(
                "A split must leave at least one event on the source application.",
            )

    def _validate_shared_connection(self) -> None:
        if (
            self._application_repository.connection
            is not self._event_repository.connection
            or self._application_repository.connection
            is not self._correction_repository.connection
        ):
            raise ApplicationSplitConflictError(
                "Manual split repositories must share one SQLite connection.",
            )


def make_manual_split_application_id(
    *,
    source_application_id: str,
    event_ids: list[str],
) -> str:
    digest_input = "\0".join((source_application_id, *sorted(event_ids)))
    digest = sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    return f"manual-split-{digest}"


def _derive_current_status(events: list[ApplicationEventRecord]) -> ApplicationStatus:
    if not events:
        return "applied"
    seen_statuses = {_EVENT_STATUS_BY_TYPE[event.event_type] for event in events}
    for status in _STATUS_PRIORITY:
        if status in seen_statuses:
            return status
    return "applied"


def _event_bounds(
    events: list[ApplicationEventRecord],
) -> tuple[datetime, datetime]:
    if not events:
        msg = "events cannot be empty"
        raise ValueError(msg)
    timestamps = sorted(event.event_at for event in events)
    return timestamps[0], timestamps[-1]


def _application_json(application: ApplicationRecord) -> JsonObject:
    return cast(JsonObject, application.model_dump(mode="json"))


def _events_json(events: list[ApplicationEventRecord]) -> list[JsonObject]:
    return [cast(JsonObject, event.model_dump(mode="json")) for event in events]


def _utcnow() -> datetime:
    return datetime.now(UTC)
