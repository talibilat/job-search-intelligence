from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
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
    start_new_application_attempt,
)
from app.pipeline.classify import AcceptedLLMExtraction, JobApplicationExtraction
from app.services.normalization import normalize_company_name, normalize_role_title

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
_ANCHORED_APPLICATION_EVENT_CATEGORIES = frozenset(
    {
        JobEmailCategory.FOLLOW_UP,
        JobEmailCategory.OTHER,
    }
)

_TERMINAL_APPLICATION_STATUSES = frozenset(
    {"offer", "rejected", "ghosted", "withdrawn"},
)
_HARD_TERMINAL_APPLICATION_STATUSES = frozenset(
    {"offer", "rejected", "withdrawn"},
)
_ACTIVE_ATTEMPT_EVENT_TYPES = frozenset(
    {"assessment", "interview_scheduled", "offer"},
)
_STALE_APPLICATION_ATTEMPT_DAYS = 365


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
        self._clock = clock or (lambda: datetime.now(UTC))
        self._run_id_factory = run_id_factory or (lambda: uuid4().hex)

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
        if application_results:
            _enrich_extractions_with_email_context(
                email_repository=self._email_repository,
                results=application_results,
            )
            application_results = _filter_anchored_application_evidence(
                application_repository=self._application_repository,
                results=application_results,
            )
        skipped_non_application_email_count = len(job_related_results) - len(application_results)

        groups: dict[ApplicationGroupingKey, list[_EnrichedExtraction]] = {}
        if application_results:
            _inherit_sparse_thread_identity(
                application_repository=self._application_repository,
                results=application_results,
            )
            groups = _group_by_key(
                application_results,
                application_repository=self._application_repository,
                event_repository=self._event_repository,
            )

        should_commit = not self._application_repository.connection.in_transaction
        with self._application_repository.transaction():
            affected_application_ids, replacement_conflicts = _remove_stale_reclassified_events(
                application_repository=self._application_repository,
                event_repository=self._event_repository,
                groups=groups,
                reclassified_email_ids={
                    result.classification.email_id for result in accepted_results
                },
            )
            for replacement_conflict in replacement_conflicts:
                manual_conflict_count += 1
                if replacement_conflict.application_id not in manual_conflict_application_ids:
                    manual_conflict_application_ids.append(replacement_conflict.application_id)
                self._record_conflict(replacement_conflict, created_at=now)

            for key, group in groups.items():
                if not group:
                    continue
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

            _refresh_reclassified_source_applications(
                application_repository=self._application_repository,
                event_repository=self._event_repository,
                affected_application_ids=affected_application_ids,
                current_application_ids={
                    make_application_id(key) for key, group in groups.items() if group
                },
                now=now,
            )

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
    """Keep lifecycle evidence and explicit thread-anchored application events."""

    return [
        _EnrichedExtraction(
            classification_email_id=result.classification.email_id,
            classification_classified_at=result.classification.classified_at,
            extraction=result.extraction,
        )
        for result in results
        if result.classification.category in _APPLICATION_LIFECYCLE_CATEGORIES
        or _is_anchored_application_event(result)
    ]


def _filter_anchored_application_evidence(
    *,
    application_repository: ApplicationRepository,
    results: list[_EnrichedExtraction],
) -> list[_EnrichedExtraction]:
    """Require response or feedback events to share an application thread."""

    batch_lifecycle_threads = {
        result.thread_id
        for result in results
        if result.thread_id is not None
        and not _is_enriched_anchored_application_event(result)
        and result.classification_email_id
    }
    known_application_threads: dict[str, bool] = {}
    anchored: list[_EnrichedExtraction] = []
    for result in results:
        if not _is_enriched_anchored_application_event(result):
            anchored.append(result)
            continue
        if result.thread_id is None:
            continue
        if result.thread_id in batch_lifecycle_threads:
            anchored.append(result)
            continue
        has_application = known_application_threads.setdefault(
            result.thread_id,
            bool(application_repository.list_by_email_thread_id(result.thread_id)),
        )
        if has_application:
            anchored.append(result)
    return anchored


def _is_anchored_application_event(result: AcceptedLLMExtraction) -> bool:
    return (
        result.classification.category in _ANCHORED_APPLICATION_EVENT_CATEGORIES
        and result.extraction.event_type in {"feedback", "response"}
    )


def _is_enriched_anchored_application_event(result: _EnrichedExtraction) -> bool:
    return result.extraction.event_type in {"feedback", "response"}


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


def _inherit_sparse_thread_identity(
    *,
    application_repository: ApplicationRepository,
    results: list[_EnrichedExtraction],
) -> None:
    for result in results:
        extraction = result.extraction
        if result.thread_id is None or (
            extraction.company is not None and extraction.role_title is not None
        ):
            continue

        target_at = _event_at_for_result(result)
        identity_candidates: list[tuple[str, str, datetime]] = []
        for application in application_repository.list_by_email_thread_id(result.thread_id):
            if application.company and application.role_title:
                identity_candidates.append(
                    (application.company, application.role_title, application.first_seen_at),
                )
        for candidate in results:
            candidate_extraction = candidate.extraction
            if (
                candidate is result
                or candidate.thread_id != result.thread_id
                or candidate_extraction.company is None
                or candidate_extraction.role_title is None
            ):
                continue
            identity_candidates.append(
                (
                    candidate_extraction.company,
                    candidate_extraction.role_title,
                    _event_at_for_result(candidate),
                ),
            )

        compatible_candidates = [
            candidate
            for candidate in identity_candidates
            if (
                extraction.company is None
                or normalize_company_name(candidate[0])
                == normalize_company_name(extraction.company)
            )
            and (
                extraction.role_title is None
                or normalize_role_title(candidate[1]) == normalize_role_title(extraction.role_title)
            )
        ]
        prior_candidates = [
            candidate for candidate in compatible_candidates if candidate[2] <= target_at
        ]
        if prior_candidates:
            inherited_company, inherited_role, _ = max(
                prior_candidates,
                key=lambda candidate: candidate[2],
            )
        elif compatible_candidates:
            inherited_company, inherited_role, _ = min(
                compatible_candidates,
                key=lambda candidate: candidate[2],
            )
        else:
            continue

        object.__setattr__(
            result,
            "extraction",
            extraction.model_copy(
                update={
                    "company": extraction.company or inherited_company,
                    "role_title": extraction.role_title or inherited_role,
                },
            ),
        )


def _group_by_key(
    results: list[_EnrichedExtraction],
    *,
    application_repository: ApplicationRepository,
    event_repository: EventRepository,
) -> dict[ApplicationGroupingKey, list[_EnrichedExtraction]]:
    base_groups: dict[ApplicationGroupingKey, list[_EnrichedExtraction]] = {}
    for result in results:
        extraction = result.extraction
        key = build_application_grouping_key(
            company=extraction.company,
            role_title=extraction.role_title,
            thread_id=result.thread_id,
            occurred_at=_event_at_for_result(result),
        )
        base_groups.setdefault(key, []).append(result)

    groups: dict[ApplicationGroupingKey, list[_EnrichedExtraction]] = {}
    for key, group in base_groups.items():
        for attempt_key, attempt_group in _partition_application_attempts(
            key=key,
            group=group,
            application_repository=application_repository,
            event_repository=event_repository,
        ).items():
            groups.setdefault(attempt_key, []).extend(attempt_group)
    return groups


class _ApplicationAttempt:
    def __init__(
        self,
        *,
        key: ApplicationGroupingKey,
        current_status: ApplicationStatus,
        first_seen_at: datetime,
        last_activity_at: datetime,
        evidence_email_ids: set[str] | None = None,
    ) -> None:
        self.key = key
        self.current_status = current_status
        self.first_seen_at = first_seen_at
        self.last_activity_at = last_activity_at
        self.evidence_email_ids = evidence_email_ids or set()


def _partition_application_attempts(
    *,
    key: ApplicationGroupingKey,
    group: list[_EnrichedExtraction],
    application_repository: ApplicationRepository,
    event_repository: EventRepository,
) -> dict[ApplicationGroupingKey, list[_EnrichedExtraction]]:
    attempts = _load_existing_attempts(
        key=key,
        application_repository=application_repository,
        event_repository=event_repository,
    )
    partitioned: dict[ApplicationGroupingKey, list[_EnrichedExtraction]] = {}

    for result in sorted(group, key=_result_timeline_sort_key):
        event_at = _event_at_for_result(result)
        event_type = _event_type_for_result(result)
        evidence_attempt = next(
            (
                candidate
                for candidate in attempts
                if result.classification_email_id in candidate.evidence_email_ids
            ),
            None,
        )
        attempt = evidence_attempt
        if attempt is None:
            attempt = max(
                (candidate for candidate in attempts if candidate.first_seen_at <= event_at),
                key=lambda candidate: candidate.first_seen_at,
                default=None,
            )
        if attempt is None:
            if attempts:
                attempt = min(attempts, key=lambda candidate: candidate.first_seen_at)
            else:
                attempt = _ApplicationAttempt(
                    key=key,
                    current_status="applied",
                    first_seen_at=event_at,
                    last_activity_at=event_at,
                )
                attempts.append(attempt)
        elif (
            evidence_attempt is None
            and event_at > attempt.last_activity_at
            and _starts_new_application_attempt(
                event_type=event_type,
                current_status=attempt.current_status,
                inactivity=event_at - attempt.last_activity_at,
            )
        ):
            later_attempt = min(
                (candidate for candidate in attempts if candidate.first_seen_at > event_at),
                key=lambda candidate: candidate.first_seen_at,
                default=None,
            )
            if later_attempt is not None:
                attempt = later_attempt
            else:
                attempt = _ApplicationAttempt(
                    key=start_new_application_attempt(key, occurred_at=event_at),
                    current_status="applied",
                    first_seen_at=event_at,
                    last_activity_at=event_at,
                )
                attempts.append(attempt)

        partitioned.setdefault(attempt.key, []).append(result)
        attempt.evidence_email_ids.add(result.classification_email_id)
        attempt.last_activity_at = max(attempt.last_activity_at, event_at)
        event_status = _status_for_event_type(
            event_type,
            result.extraction.status,
        )
        if event_status is not None:
            attempt.current_status = _transition_current_status(
                current_status=attempt.current_status,
                event_type=event_type,
                event_status=event_status,
            )

    return partitioned


def _starts_new_application_attempt(
    *,
    event_type: ApplicationEventType,
    current_status: ApplicationStatus,
    inactivity: timedelta,
) -> bool:
    is_stale = inactivity >= timedelta(days=_STALE_APPLICATION_ATTEMPT_DAYS)
    if event_type == "applied":
        return current_status in _TERMINAL_APPLICATION_STATUSES or is_stale
    return event_type in _ACTIVE_ATTEMPT_EVENT_TYPES and (
        current_status in _HARD_TERMINAL_APPLICATION_STATUSES or is_stale
    )


def _load_existing_attempts(
    *,
    key: ApplicationGroupingKey,
    application_repository: ApplicationRepository,
    event_repository: EventRepository,
) -> list[_ApplicationAttempt]:
    attempts: list[_ApplicationAttempt] = []
    base_application_id = make_application_id(key)
    if key.thread_id is not None:
        applications = application_repository.list_by_email_thread_id(key.thread_id)
    elif key.time_window_start is not None:
        window_start = datetime.combine(key.time_window_start, time.min, tzinfo=UTC)
        applications = application_repository.list_applications(
            first_seen_from=window_start.isoformat(),
            first_seen_to=(window_start + timedelta(days=key.time_window_days)).isoformat(),
        )
    else:
        applications = []

    for application in applications:
        if normalize_company_name(application.company) != (key.normalized_company or ""):
            continue
        if normalize_role_title(application.role_title) != key.normalized_role:
            continue
        if key.thread_id is None:
            application_key = build_application_grouping_key(
                company=application.company,
                role_title=application.role_title,
                thread_id=None,
                occurred_at=application.first_seen_at,
                window_days=key.time_window_days,
            )
            if application_key != key:
                continue
        events = event_repository.list_by_application_id(application.id)
        attempt_key = key
        if application.id != base_application_id:
            attempt_key = start_new_application_attempt(
                key,
                occurred_at=application.first_seen_at,
            )
        attempts.append(
            _ApplicationAttempt(
                key=attempt_key,
                current_status=application.current_status,
                first_seen_at=application.first_seen_at,
                last_activity_at=application.last_activity_at,
                evidence_email_ids={
                    event.email_id for event in events if event.email_id is not None
                },
            )
        )
    return attempts


def _result_timeline_sort_key(result: _EnrichedExtraction) -> tuple[datetime, datetime]:
    return _event_at_for_result(result), result.classification_classified_at


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
    timestamps = sorted(
        [event.event_at for event in existing_events]
        + [_event_at_for_result(result) for result in group],
    )
    # Prefer the extraction with company/role data for display fields
    best_result = _pick_best_extraction(group)

    first_seen_at = timestamps[0].isoformat() if timestamps else now.isoformat()
    last_activity_at = timestamps[-1].isoformat() if timestamps else now.isoformat()
    created_at = now.isoformat()
    updated_at = now.isoformat()

    salary_min = existing_application.salary_min if existing_application else None
    salary_max = existing_application.salary_max if existing_application else None
    currency = existing_application.currency if existing_application else None
    location = existing_application.location if existing_application else None
    work_mode = existing_application.work_mode if existing_application else None
    seniority = existing_application.seniority if existing_application else None
    sponsorship = existing_application.sponsorship if existing_application else "unknown"
    tech_stack = list(existing_application.tech_stack) if existing_application else []
    source = existing_application.source if existing_application else "other"

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
        if ext.source != "other" and source == "other":
            source = ext.source
        tech_stack.extend(t for t in ext.tech_stack if t not in tech_stack)

    company = best_result.extraction.company or ""
    role_title = best_result.extraction.role_title or ""
    current_status = derive_current_status_from_event_timeline(
        _collect_status_timeline(group, existing_events),
    )

    proposed_application: JsonObject = {
        "id": application_id,
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

    evidence_email_ids: list[str] = []
    for result in group:
        if result.classification_email_id not in evidence_email_ids:
            evidence_email_ids.append(result.classification_email_id)
    return outcome, _CorrectionConflict(
        application_id=application_id,
        conflict_key=f"application_summary:{application_id}:{','.join(sorted(evidence_email_ids))}",
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
            ) or next(
                (
                    event
                    for event in event_repository.list_by_application_id(application_id)
                    if event.email_id == email_id
                ),
                None,
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
                        "event": {
                            "id": event_id,
                            "application_id": application_id,
                            "email_id": email_id,
                            "event_type": event_type,
                            "event_at": event_at_str,
                            "extract_note": ext.rejection_reason,
                            "extracted_status": ext.status,
                        },
                    },
                    evidence_email_id=email_id,
                )
            )
            continue
        events_upserted += 1
    return events_upserted, conflicts


def _remove_stale_reclassified_events(
    *,
    application_repository: ApplicationRepository,
    event_repository: EventRepository,
    groups: dict[ApplicationGroupingKey, list[_EnrichedExtraction]],
    reclassified_email_ids: set[str],
) -> tuple[set[str], list[_CorrectionConflict]]:
    """Replace obsolete automatic events when extraction identity changes."""

    affected_application_ids: set[str] = set()
    conflicts: list[_CorrectionConflict] = []
    blocked_email_ids: set[str] = set()

    proposals: dict[str, tuple[str, str, ApplicationEventType, str, _EnrichedExtraction]] = {}
    for key, group in groups.items():
        application_id = make_application_id(key)
        for result in group:
            event_type = _event_type_for_result(result)
            event_at = _event_at_for_result(result).isoformat()
            proposals[result.classification_email_id] = (
                application_id,
                make_event_id(
                    application_id=application_id,
                    email_id=result.classification_email_id,
                    event_type=event_type,
                    event_at=event_at,
                ),
                event_type,
                event_at,
                result,
            )

    for email_id in reclassified_email_ids:
        proposal = proposals.get(email_id)
        proposed_event_id = proposal[1] if proposal is not None else None
        stale_events = [
            event
            for event in event_repository.list_by_email_id(email_id)
            if event.id != proposed_event_id
        ]
        for stale_event in stale_events:
            source_application = application_repository.get_application(stale_event.application_id)
            if source_application is not None and source_application.manual_lock:
                if proposal is not None and stale_event.application_id == proposal[0]:
                    continue
                outcome = "manual_conflict"
            else:
                outcome = event_repository.delete_automatic_event(
                    application_id=stale_event.application_id,
                    event_id=stale_event.id,
                )
            if outcome == "deleted":
                affected_application_ids.add(stale_event.application_id)
                continue
            if outcome != "manual_conflict":
                continue
            blocked_email_ids.add(email_id)
            conflicts.append(
                _CorrectionConflict(
                    application_id=stale_event.application_id,
                    conflict_key=(f"application_event:{stale_event.application_id}:{email_id}"),
                    conflict_type="application_event",
                    existing_json={
                        "event": dict(stale_event.model_dump(mode="json")),
                    },
                    proposed_json={
                        "event": (
                            {
                                "id": proposal[1],
                                "application_id": proposal[0],
                                "email_id": email_id,
                                "event_type": proposal[2],
                                "event_at": proposal[3],
                                "extract_note": proposal[4].extraction.rejection_reason,
                                "extracted_status": proposal[4].extraction.status,
                            }
                            if proposal is not None
                            else None
                        ),
                    },
                    evidence_email_id=email_id,
                )
            )

    if blocked_email_ids:
        for key, group in groups.items():
            groups[key] = [
                result
                for result in group
                if result.classification_email_id not in blocked_email_ids
            ]
    return affected_application_ids, conflicts


def _refresh_reclassified_source_applications(
    *,
    application_repository: ApplicationRepository,
    event_repository: EventRepository,
    affected_application_ids: set[str],
    current_application_ids: set[str],
    now: datetime,
) -> None:
    for application_id in affected_application_ids - current_application_ids:
        application = application_repository.get_application(application_id)
        if application is None or application.manual_lock:
            continue
        events = event_repository.list_by_application_id(application_id)
        if not events:
            application_repository.delete_application(application_id)
            continue
        application_repository.update_timeline_bounds_and_status(
            application_id=application_id,
            first_seen_at=events[0].event_at.isoformat(),
            current_status=derive_current_status_from_events(events),
            last_activity_at=events[-1].event_at.isoformat(),
            updated_at=now.isoformat(),
        )


def _event_at_for_result(result: _EnrichedExtraction) -> datetime:
    return result.extraction.event_at or result.email_sent_at or result.classification_classified_at


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
            current_status = _transition_current_status(
                current_status=current_status,
                event_type=event.event_type,
                event_status=event_status,
            )
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


def _transition_current_status(
    *,
    current_status: ApplicationStatus,
    event_type: ApplicationEventType,
    event_status: ApplicationStatus,
) -> ApplicationStatus:
    if event_type == "response" and current_status not in {
        "applied",
        "in_review",
        "ghosted",
    }:
        return current_status
    return event_status


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
