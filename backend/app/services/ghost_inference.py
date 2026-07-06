from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.db.repositories import ApplicationRepository, EventRepository
from app.models import ApplicationEventRecord, GhostInferenceRunResponse
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
        cutoff_at = evaluated_at - timedelta(days=self._threshold_days)
        ghosted_application_ids: list[str] = []
        manual_conflict_application_ids: list[str] = []
        candidates = self._application_repository.list_ghost_inference_candidates(
            cutoff_at=cutoff_at.isoformat(),
        )

        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            for application in candidates:
                if application.manual_lock:
                    manual_conflict_application_ids.append(application.id)
                    continue

                ghosted_at = application.last_activity_at + timedelta(days=self._threshold_days)
                ghosted_at_str = ghosted_at.isoformat()
                self._event_repository.upsert_event(
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
                        "No response after configured "
                        f"{self._threshold_days}-day ghost threshold."
                    ),
                )
                events = self._event_repository.list_by_application_id(application.id)
                current_status = derive_current_status_from_events(events)
                last_activity_at = _last_event_at(events, fallback=application.last_activity_at)
                self._application_repository.update_timeline_summary(
                    application_id=application.id,
                    first_seen_at=application.first_seen_at.isoformat(),
                    current_status=current_status,
                    company=application.company,
                    role_title=application.role_title,
                    source=application.source,
                    salary_min=application.salary_min,
                    salary_max=application.salary_max,
                    currency=application.currency,
                    location=application.location,
                    work_mode=application.work_mode,
                    seniority=application.seniority,
                    sponsorship=application.sponsorship,
                    tech_stack=application.tech_stack,
                    last_activity_at=last_activity_at.isoformat(),
                    updated_at=evaluated_at.isoformat(),
                    manual_lock=False,
                )
                ghosted_application_ids.append(application.id)

        if should_commit:
            self._application_repository.connection.commit()

        return GhostInferenceRunResponse(
            evaluated_at=evaluated_at,
            threshold_days=self._threshold_days,
            applications_ghosted=len(ghosted_application_ids),
            ghosted_application_ids=ghosted_application_ids,
            manual_conflict_count=len(manual_conflict_application_ids),
            manual_conflict_application_ids=manual_conflict_application_ids,
        )


def _last_event_at(
    events: list[ApplicationEventRecord],
    *,
    fallback: datetime,
) -> datetime:
    if not events:
        return fallback
    return max(event.event_at for event in events)


def _utcnow() -> datetime:
    return datetime.now(UTC)
