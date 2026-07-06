from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.db.repositories import ApplicationRepository, EmailRepository, EventRepository
from app.db.repositories.application import ApplicationUpsertOutcome
from app.models.application import ApplicationStatus
from app.models.event import ApplicationEventRecord, ApplicationEventType
from app.pipeline.aggregate import (
    ApplicationGroupingKey,
    build_application_grouping_key,
    make_application_id,
    make_event_id,
)
from app.pipeline.classify import AcceptedLLMExtraction, JobApplicationExtraction

type Clock = Callable[[], datetime]
type RunIdFactory = Callable[[], str]
type _StatusTimelineEvent = tuple[datetime, ApplicationEventType, ApplicationStatus | None]

_STATUS_BY_EVENT_TYPE: dict[ApplicationEventType, ApplicationStatus | None] = {
    "applied": "applied",
    "response": "in_review",
    "assessment": "assessment",
    "interview_scheduled": "interview",
    "feedback": None,
    "rejection": "rejected",
    "offer": "offer",
    "ghost_inferred": "ghosted",
}

_EVENT_TYPE_BY_STATUS: dict[ApplicationStatus, ApplicationEventType] = {
    "applied": "applied",
    "in_review": "response",
    "assessment": "assessment",
    "interview": "interview_scheduled",
    "offer": "offer",
    "rejected": "rejection",
}


class AggregationRunResult(BaseModel):
    """Typed result for one aggregation run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    extraction_count: int = Field(ge=0)
    applications_upserted: int = Field(ge=0)
    events_upserted: int = Field(ge=0)
    skipped_not_job_related: int = Field(ge=0)
    manual_conflict_count: int = Field(default=0, ge=0)
    manual_conflict_application_ids: list[str] = Field(default_factory=list)
    merged_source_skip_count: int = Field(default=0, ge=0)


class AggregationService:
    """Group accepted extraction results and upsert applications with events."""

    def __init__(
        self,
        *,
        application_repository: ApplicationRepository,
        event_repository: EventRepository,
        email_repository: EmailRepository,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory | None = None,
    ) -> None:
        self._application_repository = application_repository
        self._event_repository = event_repository
        self._email_repository = email_repository
        self._clock = clock or _utcnow
        self._run_id_factory = run_id_factory or _new_run_id

    def run(
        self,
        accepted_results: list[AcceptedLLMExtraction],
    ) -> AggregationRunResult:
        """Group extraction results by grouping key and upsert applications + events.

        Idempotent: re-running the same accepted results produces the same
        applications and events without duplicates.
        """

        now = self._clock()
        run_id = self._run_id_factory()
        applications_upserted = 0
        events_upserted = 0
        skipped_not_job_related = 0
        manual_conflict_count = 0
        manual_conflict_application_ids: list[str] = []
        merged_source_skip_count = 0

        job_related_results = _filter_job_related(accepted_results)
        skipped_not_job_related = len(accepted_results) - len(job_related_results)

        if not job_related_results:
            return AggregationRunResult(
                run_id=run_id,
                started_at=now,
                completed_at=self._clock(),
                extraction_count=len(accepted_results),
                applications_upserted=0,
                events_upserted=0,
                skipped_not_job_related=skipped_not_job_related,
                manual_conflict_count=0,
                manual_conflict_application_ids=[],
                merged_source_skip_count=0,
            )

        _enrich_extractions_with_email_context(
            email_repository=self._email_repository,
            results=job_related_results,
        )

        groups = _group_by_key(job_related_results)

        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            for key, group in groups.items():
                application_upsert_outcome = _upsert_application(
                    application_repository=self._application_repository,
                    event_repository=self._event_repository,
                    key=key,
                    group=group,
                    now=now,
                )
                if application_upsert_outcome == "manual_conflict":
                    manual_conflict_count += 1
                    manual_conflict_application_ids.append(make_application_id(key))
                    continue

                if application_upsert_outcome == "merged_source":
                    merged_source_skip_count += 1
                    continue

                if application_upsert_outcome == "upserted":
                    applications_upserted += 1

                _upsert_events(
                    event_repository=self._event_repository,
                    application_id=make_application_id(key),
                    group=group,
                )
                events_upserted += len(group)

        if should_commit:
            self._application_repository.connection.commit()

        return AggregationRunResult(
            run_id=run_id,
            started_at=now,
            completed_at=self._clock(),
            extraction_count=len(accepted_results),
            applications_upserted=applications_upserted,
            events_upserted=events_upserted,
            skipped_not_job_related=skipped_not_job_related,
            manual_conflict_count=manual_conflict_count,
            manual_conflict_application_ids=manual_conflict_application_ids,
            merged_source_skip_count=merged_source_skip_count,
        )


class _EnrichedExtraction(BaseModel):
    """An accepted extraction enriched with thread_id for grouping."""

    model_config = ConfigDict(frozen=True)

    classification_email_id: str = Field(min_length=1)
    classification_classified_at: datetime
    extraction: JobApplicationExtraction
    thread_id: str | None = None
    email_sent_at: datetime | None = None


def _filter_job_related(
    results: list[AcceptedLLMExtraction],
) -> list[_EnrichedExtraction]:
    return [
        _EnrichedExtraction(
            classification_email_id=result.classification.email_id,
            classification_classified_at=result.classification.classified_at,
            extraction=result.extraction,
        )
        for result in results
        if result.classification.is_job_related
    ]


def _enrich_extractions_with_email_context(
    *,
    email_repository: EmailRepository,
    results: list[_EnrichedExtraction],
) -> None:
    for result in results:
        thread_id = email_repository.get_thread_id(result.classification_email_id)
        email_sent_at = email_repository.get_sent_at(result.classification_email_id)
        object.__setattr__(result, "thread_id", thread_id)
        object.__setattr__(result, "email_sent_at", email_sent_at)


def _group_by_key(
    results: list[_EnrichedExtraction],
) -> dict[ApplicationGroupingKey, list[_EnrichedExtraction]]:
    groups: dict[ApplicationGroupingKey, list[_EnrichedExtraction]] = {}
    for result in results:
        extraction = result.extraction
        key = build_application_grouping_key(
            company=extraction.company,
            role_title=extraction.role_title,
            thread_id=result.thread_id,
            occurred_at=_event_at_for_result(result),
        )
        if key not in groups:
            groups[key] = []
        groups[key].append(result)
    return groups


def _upsert_application(
    *,
    application_repository: ApplicationRepository,
    event_repository: EventRepository,
    key: ApplicationGroupingKey,
    group: list[_EnrichedExtraction],
    now: datetime,
) -> ApplicationUpsertOutcome:
    application_id = make_application_id(key)
    existing_events = event_repository.list_by_application_id(application_id)
    timestamps = _collect_timestamps(group, existing_events)
    # Prefer the extraction with company/role data for display fields
    best_result = _pick_best_extraction(group)

    first_seen_at = timestamps[0].isoformat() if timestamps else now.isoformat()
    last_activity_at = timestamps[-1].isoformat() if timestamps else now.isoformat()
    created_at = now.isoformat()
    updated_at = now.isoformat()

    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    location: str | None = None
    work_mode: str | None = None
    seniority: str | None = None
    sponsorship: str = "unknown"
    tech_stack: list[str] = []
    source: str = "other"

    for result in group:
        ext = result.extraction
        if ext.salary_min is not None and (salary_min is None or ext.salary_min < salary_min):
            salary_min = ext.salary_min
        if ext.salary_max is not None and (salary_max is None or ext.salary_max > salary_max):
            salary_max = ext.salary_max
        if ext.currency is not None and currency is None:
            currency = ext.currency
        if ext.location is not None and location is None:
            location = ext.location
        if ext.work_mode is not None and work_mode is None:
            work_mode = ext.work_mode
        if ext.seniority is not None and seniority is None:
            seniority = ext.seniority
        if ext.sponsorship != "unknown" and sponsorship == "unknown":
            sponsorship = ext.sponsorship
        tech_stack.extend(t for t in ext.tech_stack if t not in tech_stack)

    company = best_result.extraction.company or ""
    role_title = best_result.extraction.role_title or ""

    return application_repository.upsert_application(
        id=application_id,
        company=company,
        role_title=role_title,
        source=source,
        first_seen_at=first_seen_at,
        current_status=_derive_current_status(group, existing_events),
        last_activity_at=last_activity_at,
        created_at=created_at,
        updated_at=updated_at,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        location=location,
        work_mode=work_mode,
        seniority=seniority,
        sponsorship=sponsorship,
        tech_stack=tech_stack,
    )


def _upsert_events(
    *,
    event_repository: EventRepository,
    application_id: str,
    group: list[_EnrichedExtraction],
) -> None:
    for result in group:
        ext = result.extraction
        event_type = _event_type_for_result(result)
        event_at_str = _event_at_for_result(result).isoformat()
        email_id = result.classification_email_id

        event_id = make_event_id(
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=event_at_str,
        )

        event_repository.upsert_event(
            id=event_id,
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=event_at_str,
            extract_note=ext.rejection_reason,
        )


def _event_at_for_result(result: _EnrichedExtraction) -> datetime:
    return result.extraction.event_at or result.email_sent_at or result.classification_classified_at


def _collect_timestamps(
    group: list[_EnrichedExtraction],
    existing_events: list[ApplicationEventRecord],
) -> list[datetime]:
    return sorted(
        [event.event_at for event in existing_events]
        + [_event_at_for_result(result) for result in group],
    )


def _derive_current_status(
    group: list[_EnrichedExtraction],
    existing_events: list[ApplicationEventRecord],
) -> ApplicationStatus:
    current_status: ApplicationStatus = "applied"
    for _, event_type, extracted_status in sorted(
        _collect_status_timeline(group, existing_events),
        key=lambda event: event[0],
    ):
        event_status = _status_for_event_type(event_type, extracted_status)
        if event_status is not None:
            current_status = event_status
    return current_status


def _collect_status_timeline(
    group: list[_EnrichedExtraction],
    existing_events: list[ApplicationEventRecord],
) -> list[_StatusTimelineEvent]:
    return [
        *[(event.event_at, event.event_type, None) for event in existing_events],
        *[
            (
                _event_at_for_result(result),
                _event_type_for_result(result),
                result.extraction.status,
            )
            for result in group
        ],
    ]


def _event_type_for_result(result: _EnrichedExtraction) -> ApplicationEventType:
    if result.extraction.event_type is not None:
        return result.extraction.event_type
    if result.extraction.status is not None:
        return _EVENT_TYPE_BY_STATUS.get(result.extraction.status, "applied")
    return "applied"


def _status_for_event_type(
    event_type: ApplicationEventType,
    extracted_status: ApplicationStatus | None,
) -> ApplicationStatus | None:
    event_status = _STATUS_BY_EVENT_TYPE[event_type]
    if event_status is not None:
        return event_status
    return extracted_status


def _pick_best_extraction(
    group: list[_EnrichedExtraction],
) -> _EnrichedExtraction:
    best = group[0]
    for result in group[1:]:
        ext = result.extraction
        best_ext = best.extraction
        if ext.company is not None and best_ext.company is None:
            best = result
            continue
        if ext.role_title is not None and best_ext.role_title is None:
            best = result
            continue
    return best


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return uuid4().hex
