from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast

from app.db.repositories import ApplicationRepository, CorrectionRepository, EventRepository
from app.models.application import ApplicationStatus
from app.models.application_merge import ApplicationMergeResponse
from app.models.correction import JsonObject
from app.models.records import (
    ApplicationCorrectionRecord,
    ApplicationEventRecord,
    ApplicationRecord,
)

type Clock = Callable[[], datetime]
type MissingApplicationRole = Literal["target", "source"]


class _MergedApplicationSummary(TypedDict):
    id: str
    company: str
    role_title: str
    source: str
    first_seen_at: str
    current_status: str
    salary_min: int | None
    salary_max: int | None
    currency: str | None
    location: str | None
    work_mode: str | None
    seniority: str | None
    sponsorship: str
    tech_stack: list[str]
    last_activity_at: str
    manual_lock: bool
    updated_at: str


class ManualMergeInvalidRequestError(Exception):
    """Raised when a manual merge request cannot be applied."""


class ManualMergeNotFoundError(Exception):
    """Raised when a requested application is missing."""

    def __init__(self, *, application_id: str, role: MissingApplicationRole) -> None:
        self.application_id = application_id
        self.role = role
        super().__init__(f"{role} application not found: {application_id}")


class ManualApplicationMergeService:
    """Apply audited manual application merges."""

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

    def merge_applications(
        self,
        *,
        target_application_id: str,
        source_application_id: str,
        reason: str | None,
    ) -> ApplicationMergeResponse:
        if target_application_id == source_application_id:
            raise ManualMergeInvalidRequestError(
                "cannot merge an application into itself",
            )

        now = self._clock()
        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            target = self._load_application(
                application_id=target_application_id,
                role="target",
            )
            source = self._load_application(
                application_id=source_application_id,
                role="source",
            )
            source_events = self._event_repository.list_by_application_id(
                source_application_id,
            )
            source_corrections = self._correction_repository.list_by_application_id(
                source_application_id,
            )

            before_json: JsonObject = {
                "target_application": _json_object(target),
                "source_application": _json_object(source),
                "source_events": [_json_object(event) for event in source_events],
                "source_corrections": [
                    _json_object(correction) for correction in source_corrections
                ],
            }
            merged = _merge_application_summary(
                target=target,
                source=source,
                updated_at=now,
            )

            self._application_repository.update_application_summary(**merged)
            moved_event_count = self._event_repository.reassign_application_events(
                source_application_id=source_application_id,
                target_application_id=target_application_id,
            )
            self._correction_repository.reassign_application_corrections(
                source_application_id=source_application_id,
                target_application_id=target_application_id,
            )
            self._application_repository.delete_application(source_application_id)

            updated_target = self._load_application(
                application_id=target_application_id,
                role="target",
            )
            correction = self._correction_repository.create_correction(
                application_id=target_application_id,
                correction_type="merge",
                before_json=before_json,
                after_json={
                    "target_application": _json_object(updated_target),
                    "deleted_source_application_id": source_application_id,
                    "moved_event_ids": [event.id for event in source_events],
                    "moved_correction_ids": [correction.id for correction in source_corrections],
                },
                reason=reason,
                created_at=now.isoformat(),
            )

        if should_commit:
            self._application_repository.connection.commit()

        return ApplicationMergeResponse(
            target_application_id=target_application_id,
            source_application_id=source_application_id,
            moved_event_count=moved_event_count,
            application=updated_target,
            correction=correction,
        )

    def _load_application(
        self,
        *,
        application_id: str,
        role: MissingApplicationRole,
    ) -> ApplicationRecord:
        application = self._application_repository.get_application(application_id)
        if application is None:
            raise ManualMergeNotFoundError(
                application_id=application_id,
                role=role,
            )
        return application


def _merge_application_summary(
    *,
    target: ApplicationRecord,
    source: ApplicationRecord,
    updated_at: datetime,
) -> _MergedApplicationSummary:
    return {
        "id": target.id,
        "company": target.company,
        "role_title": target.role_title,
        "source": target.source,
        "first_seen_at": min(target.first_seen_at, source.first_seen_at).isoformat(),
        "current_status": _derive_current_status(
            target.current_status,
            source.current_status,
        ),
        "salary_min": _min_optional(target.salary_min, source.salary_min),
        "salary_max": _max_optional(target.salary_max, source.salary_max),
        "currency": target.currency or source.currency,
        "location": target.location or source.location,
        "work_mode": target.work_mode or source.work_mode,
        "seniority": target.seniority or source.seniority,
        "sponsorship": (
            source.sponsorship if target.sponsorship == "unknown" else target.sponsorship
        ),
        "tech_stack": _merge_tech_stack(target.tech_stack, source.tech_stack),
        "last_activity_at": max(
            target.last_activity_at,
            source.last_activity_at,
        ).isoformat(),
        "manual_lock": True,
        "updated_at": updated_at.isoformat(),
    }


def _derive_current_status(
    target_status: ApplicationStatus,
    source_status: ApplicationStatus,
) -> ApplicationStatus:
    status_priority: list[ApplicationStatus] = [
        "offer",
        "rejected",
        "withdrawn",
        "interview",
        "assessment",
        "in_review",
        "ghosted",
        "applied",
    ]
    statuses = {target_status, source_status}
    for status in status_priority:
        if status in statuses:
            return status
    return "applied"


def _min_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _max_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def _merge_tech_stack(target: list[str], source: list[str]) -> list[str]:
    merged = list(target)
    for item in source:
        if item not in merged:
            merged.append(item)
    return merged


def _json_object(
    model: ApplicationRecord | ApplicationEventRecord | ApplicationCorrectionRecord,
) -> JsonObject:
    return cast(JsonObject, model.model_dump(mode="json"))
