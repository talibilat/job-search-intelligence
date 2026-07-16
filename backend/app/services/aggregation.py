from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.db.repositories import (
    ApplicationRepository,
    CorrectionConflictRepository,
    EmailRepository,
    EventRepository,
)
from app.db.repositories.application import ApplicationUpsertOutcome
from app.models.application import ApplicationStatus
from app.models.classification import JobEmailCategory
from app.models.event import ApplicationEventRecord, ApplicationEventType
from app.models.records import CorrectionConflictType, JsonObject
from app.pipeline.aggregate import (
    ApplicationGroupingKey,
    build_application_grouping_key,
    make_application_id,
    make_event_id,
)
from app.pipeline.classify import AcceptedLLMExtraction, JobApplicationExtraction

type Clock = Callable[[], datetime]
type RunIdFactory = Callable[[], str]

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

_APPLICATION_LIFECYCLE_CATEGORIES = frozenset(
    {
        JobEmailCategory.APPLICATION_CONFIRMATION,
        JobEmailCategory.REJECTION,
        JobEmailCategory.INTERVIEW_INVITE,
        JobEmailCategory.OFFER,
        JobEmailCategory.ASSESSMENT,
    }
)


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
    skipped_non_application_email_count: int = Field(default=0, ge=0)
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
        correction_conflict_repository: CorrectionConflictRepository,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory | None = None,
    ) -> None:
        self._application_repository = application_repository
        self._event_repository = event_repository
        self._email_repository = email_repository
        self._correction_conflict_repository = correction_conflict_repository
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

        job_related_results = [
            result for result in accepted_results if result.classification.is_job_related
        ]
        skipped_not_job_related = len(accepted_results) - len(job_related_results)
        application_results = _filter_application_evidence(job_related_results)
        skipped_non_application_email_count = len(job_related_results) - len(application_results)

        if not application_results:
            return AggregationRunResult(
                run_id=run_id,
                started_at=now,
                completed_at=self._clock(),
                extraction_count=len(accepted_results),
                applications_upserted=0,
                events_upserted=0,
                skipped_not_job_related=skipped_not_job_related,
                skipped_non_application_email_count=skipped_non_application_email_count,
                manual_conflict_count=0,
                manual_conflict_application_ids=[],
                merged_source_skip_count=0,
            )

        _enrich_extractions_with_email_context(
            email_repository=self._email_repository,
            results=application_results,
        )

        groups = _group_by_key(application_results)

        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            for key, group in groups.items():
                application_upsert_outcome, application_conflict = _upsert_application(
                    application_repository=self._application_repository,
                    event_repository=self._event_repository,
                    key=key,
                    group=group,
                    now=now,
                )
                if application_upsert_outcome == "manual_conflict":
                    manual_conflict_count += 1
                    manual_conflict_application_ids.append(make_application_id(key))
                    if application_conflict is not None:
                        self._record_conflict(application_conflict, created_at=now)
                    continue

                if application_upsert_outcome == "merged_source":
                    merged_source_skip_count += 1
                    continue

                if application_upsert_outcome == "upserted":
                    applications_upserted += 1

                event_conflicts: list[_CorrectionConflict]
                events_upserted_for_group, event_conflicts = _upsert_events(
                    event_repository=self._event_repository,
                    application_id=make_application_id(key),
                    group=group,
                )
                events_upserted += events_upserted_for_group
                if event_conflicts:
                    manual_conflict_count += 1
                    application_id = make_application_id(key)
                    if application_id not in manual_conflict_application_ids:
                        manual_conflict_application_ids.append(application_id)
                    for event_conflict in event_conflicts:
                        self._record_conflict(event_conflict, created_at=now)

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
            skipped_non_application_email_count=skipped_non_application_email_count,
            manual_conflict_count=manual_conflict_count,
            manual_conflict_application_ids=manual_conflict_application_ids,
            merged_source_skip_count=merged_source_skip_count,
        )

    def _record_conflict(
        self,
        conflict: _CorrectionConflict,
        *,
        created_at: datetime,
    ) -> None:
        self._correction_conflict_repository.upsert_conflict(
            application_id=conflict.application_id,
            conflict_key=conflict.conflict_key,
            conflict_type=conflict.conflict_type,
            existing_json=conflict.existing_json,
            proposed_json=conflict.proposed_json,
            evidence_email_id=conflict.evidence_email_id,
            created_at=created_at.isoformat(),
        )


class _EnrichedExtraction(BaseModel):
    """An accepted extraction enriched with thread_id for grouping."""

    model_config = ConfigDict(frozen=True)

    classification_email_id: str = Field(min_length=1)
    classification_classified_at: datetime
    extraction: JobApplicationExtraction
    thread_id: str | None = None
    email_sent_at: datetime | None = None


class _StatusTimelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_at: datetime
    email_sent_at: datetime
    classified_at: datetime
    event_type: ApplicationEventType
    extracted_status: ApplicationStatus | None


class _CorrectionConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    application_id: str
    conflict_key: str
    conflict_type: CorrectionConflictType
    existing_json: JsonObject
    proposed_json: JsonObject
    evidence_email_id: str | None


def _filter_application_evidence(
    results: list[AcceptedLLMExtraction],
) -> list[_EnrichedExtraction]:
    """Keep submitted-application lifecycle evidence out of general job mail."""

    return [
        _EnrichedExtraction(
            classification_email_id=result.classification.email_id,
            classification_classified_at=result.classification.classified_at,
            extraction=result.extraction,
        )
        for result in results
        if result.classification.category in _APPLICATION_LIFECYCLE_CATEGORIES
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
) -> tuple[ApplicationUpsertOutcome, _CorrectionConflict | None]:
    application_id = make_application_id(key)
    existing_application = application_repository.get_application(application_id)
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
    current_status = _derive_current_status(group, existing_events)

    proposed_application = _proposed_application_json(
        id=application_id,
        company=company,
        role_title=role_title,
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
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

    outcome = application_repository.upsert_application(
        id=application_id,
        company=company,
        role_title=role_title,
        source=source,
        first_seen_at=first_seen_at,
        current_status=current_status,
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
    if outcome != "manual_conflict" or existing_application is None:
        return outcome, None

    evidence_email_ids = _evidence_email_ids(group)
    return outcome, _CorrectionConflict(
        application_id=application_id,
        conflict_key=f"application_summary:{application_id}:{_evidence_key(evidence_email_ids)}",
        conflict_type="application_summary",
        existing_json={
            "application": dict(existing_application.model_dump(mode="json")),
        },
        proposed_json={
            "application": proposed_application,
            "evidence_email_ids": evidence_email_ids,
        },
        evidence_email_id=evidence_email_ids[0] if evidence_email_ids else None,
    )


def _upsert_events(
    *,
    event_repository: EventRepository,
    application_id: str,
    group: list[_EnrichedExtraction],
) -> tuple[int, list[_CorrectionConflict]]:
    events_upserted = 0
    conflicts: list[_CorrectionConflict] = []
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

        outcome = event_repository.upsert_event(
            id=event_id,
            application_id=application_id,
            email_id=email_id,
            event_type=event_type,
            event_at=event_at_str,
            extract_note=ext.rejection_reason,
            extracted_status=ext.status,
        )
        if outcome == "manual_conflict":
            existing_event = event_repository.get_by_application_and_id(
                application_id=application_id,
                event_id=event_id,
            ) or _find_existing_event_for_email(
                event_repository=event_repository,
                application_id=application_id,
                email_id=email_id,
            )
            conflicts.append(
                _CorrectionConflict(
                    application_id=application_id,
                    conflict_key=(f"application_event:{application_id}:{email_id or event_id}"),
                    conflict_type="application_event",
                    existing_json={
                        "event": (
                            dict(existing_event.model_dump(mode="json")) if existing_event else None
                        ),
                    },
                    proposed_json={
                        "event": _proposed_event_json(
                            id=event_id,
                            application_id=application_id,
                            email_id=email_id,
                            event_type=event_type,
                            event_at=event_at_str,
                            extract_note=ext.rejection_reason,
                            extracted_status=ext.status,
                        ),
                    },
                    evidence_email_id=email_id,
                )
            )
            continue
        events_upserted += 1
    return events_upserted, conflicts


def _find_existing_event_for_email(
    *,
    event_repository: EventRepository,
    application_id: str,
    email_id: str | None,
) -> ApplicationEventRecord | None:
    if email_id is None:
        return None
    for event in event_repository.list_by_application_id(application_id):
        if event.email_id == email_id:
            return event
    return None


def _proposed_application_json(
    *,
    id: str,
    company: str,
    role_title: str,
    source: str,
    first_seen_at: str,
    current_status: ApplicationStatus,
    last_activity_at: str,
    created_at: str,
    updated_at: str,
    salary_min: int | None,
    salary_max: int | None,
    currency: str | None,
    location: str | None,
    work_mode: str | None,
    seniority: str | None,
    sponsorship: str,
    tech_stack: list[str],
) -> JsonObject:
    return {
        "id": id,
        "company": company,
        "role_title": role_title,
        "source": source,
        "first_seen_at": first_seen_at,
        "current_status": current_status,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "location": location,
        "work_mode": work_mode,
        "seniority": seniority,
        "sponsorship": sponsorship,
        "tech_stack": tech_stack,
        "last_activity_at": last_activity_at,
        "manual_lock": False,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _proposed_event_json(
    *,
    id: str,
    application_id: str,
    email_id: str | None,
    event_type: ApplicationEventType,
    event_at: str,
    extract_note: str | None,
    extracted_status: ApplicationStatus | None,
) -> JsonObject:
    return {
        "id": id,
        "application_id": application_id,
        "email_id": email_id,
        "event_type": event_type,
        "event_at": event_at,
        "extract_note": extract_note,
        "extracted_status": extracted_status,
    }


def _evidence_email_ids(group: list[_EnrichedExtraction]) -> list[str]:
    email_ids: list[str] = []
    for result in group:
        if result.classification_email_id not in email_ids:
            email_ids.append(result.classification_email_id)
    return email_ids


def _evidence_key(email_ids: list[str]) -> str:
    if not email_ids:
        return "unknown"
    return ",".join(sorted(email_ids))


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
    return derive_current_status_from_event_timeline(
        _collect_status_timeline(group, existing_events),
    )


def derive_current_status_from_events(
    events: list[ApplicationEventRecord],
) -> ApplicationStatus:
    return derive_current_status_from_event_timeline(
        [
            _StatusTimelineEvent(
                event_at=event.event_at,
                email_sent_at=event.email_sent_at or event.event_at,
                classified_at=(
                    event.classification_classified_at or event.email_sent_at or event.event_at
                ),
                event_type=event.event_type,
                extracted_status=event.extracted_status,
            )
            for event in events
        ],
    )


def derive_current_status_from_event_timeline(
    events: list[_StatusTimelineEvent],
) -> ApplicationStatus:
    current_status: ApplicationStatus = "applied"
    for event in sorted(events, key=_status_timeline_sort_key):
        event_status = _status_for_event_type(event.event_type, event.extracted_status)
        if event_status is not None:
            current_status = event_status
    return current_status


def _collect_status_timeline(
    group: list[_EnrichedExtraction],
    existing_events: list[ApplicationEventRecord],
) -> list[_StatusTimelineEvent]:
    return [
        *[
            _StatusTimelineEvent(
                event_at=event.event_at,
                email_sent_at=event.email_sent_at or event.event_at,
                classified_at=(
                    event.classification_classified_at or event.email_sent_at or event.event_at
                ),
                event_type=event.event_type,
                extracted_status=event.extracted_status,
            )
            for event in existing_events
        ],
        *[
            _StatusTimelineEvent(
                event_at=_event_at_for_result(result),
                email_sent_at=result.email_sent_at or _event_at_for_result(result),
                classified_at=result.classification_classified_at,
                event_type=_event_type_for_result(result),
                extracted_status=result.extraction.status,
            )
            for result in group
        ],
    ]


def _status_timeline_sort_key(
    event: _StatusTimelineEvent,
) -> tuple[datetime, datetime, datetime]:
    return event.event_at, event.email_sent_at, event.classified_at


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
