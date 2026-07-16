from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.db.repositories import ApplicationRepository, EventRepository
from app.models import ApplicationEventRecord
from app.models.event import RESPONSE_LIKE_APPLICATION_EVENT_TYPES, ApplicationEventType
from app.models.ghost_inference import GhostInferenceRunResponse
from app.pipeline.aggregate import make_event_id
from app.services.aggregation import derive_current_status_from_events

type Clock = Callable[[], datetime]


class GhostInferenceService:
    """Infer ghosted applications from silent event timelines."""

    def __init__(
        self,
        *,
        application_repository: ApplicationRepository,
        event_repository: EventRepository,
        threshold_days: int,
        clock: Clock | None = None,
    ) -> None:
        self._application_repository = application_repository
        self._event_repository = event_repository
        self._threshold_days = threshold_days
        self._clock = clock or _utcnow

    def run(self) -> GhostInferenceRunResponse:
        evaluated_at = self._clock()
        ghosted_application_ids: list[str] = []
        manual_conflict_application_ids: list[str] = []
        retracted_application_ids: list[str] = []

        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            retracted_application_ids = self._reconcile_existing_ghosts(
                evaluated_at=evaluated_at,
                manual_conflict_application_ids=manual_conflict_application_ids,
            )
            cutoff_at = evaluated_at - timedelta(days=self._threshold_days)
            candidates = self._application_repository.list_ghost_inference_candidates(
                cutoff_at=cutoff_at.isoformat(),
            )
            for application in candidates:
                if application.manual_lock:
                    manual_conflict_application_ids.append(application.id)
                    continue

                events = self._event_repository.list_by_application_id(application.id)
                non_ghost_events = [
                    event for event in events if event.event_type != "ghost_inferred"
                ]
                latest_applied = _latest_event(non_ghost_events, event_type="applied")
                if latest_applied is None or _has_response_after_latest_applied(
                    non_ghost_events,
                    latest_applied=latest_applied,
                ):
                    continue

                latest_non_ghost = _latest_event(non_ghost_events)
                if latest_non_ghost is None:
                    continue

                ghosted_at = latest_non_ghost.event_at + timedelta(days=self._threshold_days)
                ghosted_at_str = ghosted_at.isoformat()
                outcome = self._event_repository.upsert_event(
                    id=make_event_id(
                        application_id=application.id,
                        email_id=None,
                        event_type="ghost_inferred",
                        event_at=ghosted_at_str,
                    ),
                    application_id=application.id,
                    email_id=None,
                    event_type="ghost_inferred",
                    event_at=ghosted_at_str,
                    extract_note=(
                        f"No response after configured {self._threshold_days}-day ghost threshold."
                    ),
                )
                if outcome != "upserted":
                    manual_conflict_application_ids.append(application.id)
                    continue

                self._update_application_from_timeline(
                    application_id=application.id,
                    fallback_last_activity_at=application.last_activity_at,
                    evaluated_at=evaluated_at,
                )
                ghosted_application_ids.append(application.id)

        if should_commit:
            self._application_repository.connection.commit()

        return GhostInferenceRunResponse(
            evaluated_at=evaluated_at,
            threshold_days=self._threshold_days,
            applications_ghosted=len(ghosted_application_ids),
            ghosted_application_ids=ghosted_application_ids,
            ghost_retraction_count=len(retracted_application_ids),
            retracted_application_ids=retracted_application_ids,
            manual_conflict_count=len(manual_conflict_application_ids),
            manual_conflict_application_ids=manual_conflict_application_ids,
        )

    def _reconcile_existing_ghosts(
        self,
        *,
        evaluated_at: datetime,
        manual_conflict_application_ids: list[str],
    ) -> list[str]:
        retracted_application_ids: list[str] = []
        ghosted_applications = (
            self._application_repository.list_applications_with_ghost_inferred_events()
        )
        for application in ghosted_applications:
            events = self._event_repository.list_by_application_id(application.id)
            ghost_events = [event for event in events if event.event_type == "ghost_inferred"]
            if not ghost_events:
                continue
            if application.manual_lock:
                manual_conflict_application_ids.append(application.id)
                continue

            non_ghost_events = [event for event in events if event.event_type != "ghost_inferred"]
            latest_applied = _latest_event(non_ghost_events, event_type="applied")
            latest_non_ghost = _latest_event(non_ghost_events)
            if latest_non_ghost is None:
                latest_non_ghost_at = application.last_activity_at
            else:
                latest_non_ghost_at = latest_non_ghost.event_at
            expected_ghosted_at = latest_non_ghost_at + timedelta(days=self._threshold_days)
            has_response_after_latest_applied = latest_applied is not None and (
                _has_response_after_latest_applied(
                    non_ghost_events,
                    latest_applied=latest_applied,
                )
            )
            ghost_dates_are_current = (
                len(ghost_events) == 1 and ghost_events[0].event_at == expected_ghosted_at
            )
            should_retract = (
                latest_applied is None
                or has_response_after_latest_applied
                or expected_ghosted_at > evaluated_at
                or not ghost_dates_are_current
            )
            if not should_retract:
                continue

            delete_outcome = self._event_repository.delete_ghost_inferred_events_for_application(
                application.id,
            )
            if delete_outcome == "manual_conflict":
                manual_conflict_application_ids.append(application.id)
                continue
            if delete_outcome == "not_found":
                continue

            retracted_application_ids.append(application.id)
            self._update_application_from_timeline(
                application_id=application.id,
                fallback_last_activity_at=latest_non_ghost_at,
                evaluated_at=evaluated_at,
            )
        return retracted_application_ids

    def _update_application_from_timeline(
        self,
        *,
        application_id: str,
        fallback_last_activity_at: datetime,
        evaluated_at: datetime,
    ) -> None:
        events = self._event_repository.list_by_application_id(application_id)
        current_status = derive_current_status_from_events(events)
        last_activity_at = _last_event_at(events, fallback=fallback_last_activity_at)
        self._application_repository.update_timeline_status(
            application_id=application_id,
            current_status=current_status,
            last_activity_at=last_activity_at.isoformat(),
            updated_at=evaluated_at.isoformat(),
        )


def _last_event_at(
    events: list[ApplicationEventRecord],
    *,
    fallback: datetime,
) -> datetime:
    if not events:
        return fallback
    return max(event.event_at for event in events)


def _latest_event(
    events: list[ApplicationEventRecord],
    *,
    event_type: ApplicationEventType | None = None,
) -> ApplicationEventRecord | None:
    matching_events = [
        event for event in events if event_type is None or event.event_type == event_type
    ]
    if not matching_events:
        return None
    return max(matching_events, key=_event_ordering_key)


def _has_response_after_latest_applied(
    events: list[ApplicationEventRecord],
    *,
    latest_applied: ApplicationEventRecord,
) -> bool:
    latest_applied_key = _event_ordering_key(latest_applied)
    return any(
        event.event_type in RESPONSE_LIKE_APPLICATION_EVENT_TYPES
        and _event_ordering_key(event) > latest_applied_key
        for event in events
    )


def _event_ordering_key(
    event: ApplicationEventRecord,
) -> tuple[datetime, datetime, datetime, str]:
    email_sent_at = event.email_sent_at or event.event_at
    classified_at = event.classification_classified_at or email_sent_at
    return event.event_at, email_sent_at, classified_at, event.id


def _utcnow() -> datetime:
    return datetime.now(UTC)
