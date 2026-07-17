from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import ValidationError

from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.models.application import ApplicationStatus
from app.models.application_edit import (
    ApplicationEventEditResponse,
    ApplicationStatusEditResponse,
)
from app.models.correction import JsonObject
from app.models.event import ApplicationEventRecord, ApplicationEventType
from app.models.records import ApplicationCorrectionRecord, ApplicationRecord
from app.pipeline.aggregate import make_event_id
from app.services.aggregation import derive_current_status_from_events

type Clock = Callable[[], datetime]
type MissingManualEditResource = Literal["application", "event"]


class ManualEditNotFoundError(Exception):
    """Raised when a requested manual edit target is missing."""

    def __init__(
        self,
        *,
        resource: MissingManualEditResource,
        resource_id: str,
    ) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} not found: {resource_id}")


class ManualEditInvalidRequestError(Exception):
    """Raised when a manual edit would violate application/event invariants."""


class ManualApplicationEditService:
    """Apply audited manual status and event edits."""

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
        self._clock = clock or (lambda: datetime.now(UTC))

    def edit_status(
        self,
        *,
        application_id: str,
        current_status: ApplicationStatus,
        reason: str | None,
    ) -> ApplicationStatusEditResponse:
        now = self._clock()
        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            application = self._load_application(application_id)
            before_json: JsonObject = {"application": _json_object(application)}

            self._update_application_summary(
                application=application,
                current_status=current_status,
                last_activity_at=application.last_activity_at,
                updated_at=now,
            )
            updated_application = self._load_application(application_id)
            correction = self._correction_repository.create_correction(
                application_id=application_id,
                correction_type="status_edit",
                before_json=before_json,
                after_json={"application": _json_object(updated_application)},
                reason=reason,
                created_at=now.isoformat(),
            )

        if should_commit:
            self._application_repository.connection.commit()

        return ApplicationStatusEditResponse(
            application=updated_application,
            correction=correction,
        )

    def edit_event(
        self,
        *,
        application_id: str,
        event_id: str,
        reason: str | None,
        event_type: ApplicationEventType | None = None,
        event_at: datetime | None = None,
        email_id: str | None = None,
        extract_note: str | None = None,
        update_email_id: bool | None = None,
        update_extract_note: bool | None = None,
    ) -> ApplicationEventEditResponse:
        now = self._clock()
        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            application = self._load_application(application_id)
            event = self._load_event(application_id=application_id, event_id=event_id)
            updated_event = _build_updated_event(
                event=event,
                event_type=event_type,
                event_at=event_at,
                email_id=email_id,
                extract_note=extract_note,
                update_email_id=update_email_id,
                update_extract_note=update_extract_note,
            )
            if _events_match(event, updated_event):
                raise ManualEditInvalidRequestError("application event edit is a no-op")
            self._validate_event_email(updated_event)
            new_event_id = _event_id_for_updated_event(
                original_event=event,
                updated_event=updated_event,
            )
            if (
                new_event_id != event.id
                and self._event_repository.get_by_application_and_id(
                    application_id=application_id,
                    event_id=new_event_id,
                )
                is not None
            ):
                raise ManualEditInvalidRequestError("application event already exists")
            updated_event = updated_event.model_copy(update={"id": new_event_id})
            before_json: JsonObject = {
                "application": _json_object(application),
                "event": _json_object(event),
            }

            self._event_repository.update_event(
                id=event_id,
                new_id=updated_event.id,
                application_id=application_id,
                email_id=updated_event.email_id,
                event_type=updated_event.event_type,
                event_at=updated_event.event_at.isoformat(),
                extract_note=updated_event.extract_note,
                extracted_status=updated_event.extracted_status,
            )
            stored_event = self._load_event(
                application_id=application_id,
                event_id=updated_event.id,
            )
            last_activity_at = max(
                event.event_at
                for event in self._event_repository.list_by_application_id(application_id)
            )
            self._update_application_summary(
                application=application,
                current_status=_derive_current_status(
                    self._event_repository.list_by_application_id(application_id)
                ),
                last_activity_at=last_activity_at,
                updated_at=now,
            )
            updated_application = self._load_application(application_id)
            correction = self._correction_repository.create_correction(
                application_id=application_id,
                correction_type="event_edit",
                before_json=before_json,
                after_json={
                    "application": _json_object(updated_application),
                    "event": _json_object(stored_event),
                },
                reason=reason,
                created_at=now.isoformat(),
            )

        if should_commit:
            self._application_repository.connection.commit()

        return ApplicationEventEditResponse(
            application=updated_application,
            event=stored_event,
            correction=correction,
        )

    def _load_application(self, application_id: str) -> ApplicationRecord:
        application = self._application_repository.get_application(application_id)
        if application is None:
            raise ManualEditNotFoundError(
                resource="application",
                resource_id=application_id,
            )
        return application

    def _load_event(self, *, application_id: str, event_id: str) -> ApplicationEventRecord:
        event = self._event_repository.get_by_application_and_id(
            application_id=application_id,
            event_id=event_id,
        )
        if event is None:
            raise ManualEditNotFoundError(resource="event", resource_id=event_id)
        return event

    def _validate_event_email(self, event: ApplicationEventRecord) -> None:
        if event.email_id is None:
            return
        if not self._event_repository.raw_email_exists(event.email_id):
            raise ManualEditInvalidRequestError("application event email does not exist")

    def _update_application_summary(
        self,
        *,
        application: ApplicationRecord,
        current_status: ApplicationStatus,
        last_activity_at: datetime,
        updated_at: datetime,
    ) -> None:
        self._application_repository.update_application_summary(
            id=application.id,
            company=application.company,
            role_title=application.role_title,
            source=application.source,
            first_seen_at=application.first_seen_at.isoformat(),
            current_status=current_status,
            last_activity_at=last_activity_at.isoformat(),
            updated_at=updated_at.isoformat(),
            salary_min=application.salary_min,
            salary_max=application.salary_max,
            currency=application.currency,
            location=application.location,
            work_mode=application.work_mode,
            seniority=application.seniority,
            sponsorship=application.sponsorship,
            tech_stack=application.tech_stack,
            manual_lock=True,
        )


def _build_updated_event(
    *,
    event: ApplicationEventRecord,
    event_type: ApplicationEventType | None,
    event_at: datetime | None,
    email_id: str | None,
    extract_note: str | None,
    update_email_id: bool | None,
    update_extract_note: bool | None,
) -> ApplicationEventRecord:
    should_update_email_id = (
        update_email_id if update_email_id is not None else email_id is not None
    )
    should_update_extract_note = (
        update_extract_note if update_extract_note is not None else extract_note is not None
    )
    try:
        return ApplicationEventRecord(
            id=event.id,
            application_id=event.application_id,
            email_id=email_id if should_update_email_id else event.email_id,
            event_type=event_type or event.event_type,
            event_at=event_at or event.event_at,
            extract_note=extract_note if should_update_extract_note else event.extract_note,
            extracted_status=(
                event.extracted_status
                if event_type is None or event_type == event.event_type
                else None
            ),
        )
    except ValidationError as error:
        raise ManualEditInvalidRequestError("invalid application event edit") from error


def _events_match(
    original: ApplicationEventRecord,
    updated: ApplicationEventRecord,
) -> bool:
    return (
        original.email_id == updated.email_id
        and original.event_type == updated.event_type
        and original.event_at == updated.event_at
        and original.extract_note == updated.extract_note
    )


def _event_id_for_updated_event(
    *,
    original_event: ApplicationEventRecord,
    updated_event: ApplicationEventRecord,
) -> str:
    if (
        original_event.email_id == updated_event.email_id
        and original_event.event_type == updated_event.event_type
        and original_event.event_at == updated_event.event_at
    ):
        return original_event.id

    return make_event_id(
        application_id=updated_event.application_id,
        email_id=updated_event.email_id,
        event_type=updated_event.event_type,
        event_at=updated_event.event_at.isoformat(),
    )


def _derive_current_status(events: list[ApplicationEventRecord]) -> ApplicationStatus:
    return derive_current_status_from_events(events)


def _json_object(
    model: ApplicationRecord | ApplicationEventRecord | ApplicationCorrectionRecord,
) -> JsonObject:
    return cast(JsonObject, model.model_dump(mode="json"))
