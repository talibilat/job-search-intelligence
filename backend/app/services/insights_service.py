from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.db.repositories import InsightRepository
from app.models import InsightInput, InsightInputFact
from app.models.records import ApplicationEventType, ApplicationStatus, InsightType


class InsightInputBuilder:
    """Build deterministic, cited input packages for narrative insight synthesis."""

    def __init__(self, insight_repository: InsightRepository) -> None:
        self._insight_repository = insight_repository

    def build(
        self,
        insight_type: InsightType,
        *,
        max_evidence_items: int = 100,
    ) -> InsightInput:
        if max_evidence_items < 1:
            msg = "max_evidence_items must be at least 1"
            raise ValueError(msg)

        scope = _evidence_scope(insight_type)
        scoped_evidence = self._insight_repository.list_input_evidence(
            application_statuses=scope.application_statuses,
            event_types=scope.event_types,
            newest_first=scope.newest_first,
        )
        insight_input = InsightInput(
            type=insight_type,
            facts=self._build_facts(),
            evidence=scoped_evidence[:max_evidence_items],
            source_fingerprint=_hash_payload(
                [item.model_dump(mode="json") for item in scoped_evidence],
            ),
            inputs_hash="",
        )
        return insight_input.model_copy(
            update={"inputs_hash": _hash_insight_input(insight_input)},
        )

    def _build_facts(self) -> list[InsightInputFact]:
        return [
            InsightInputFact(
                name="total_applications",
                value=self._insight_repository.count_applications(),
                source="applications",
            ),
            InsightInputFact(
                name="status_counts",
                value=self._insight_repository.count_applications_by_status(),
                source="applications",
            ),
            InsightInputFact(
                name="source_counts",
                value=self._insight_repository.count_applications_by_source(),
                source="applications",
            ),
            InsightInputFact(
                name="sponsorship_counts",
                value=self._insight_repository.count_applications_by_sponsorship(),
                source="applications",
            ),
            InsightInputFact(
                name="work_mode_counts",
                value=self._insight_repository.count_applications_by_work_mode(),
                source="applications",
            ),
            InsightInputFact(
                name="event_type_counts",
                value=self._insight_repository.count_events_by_type(),
                source="application_events",
            ),
        ]


def _hash_insight_input(insight_input: InsightInput) -> str:
    payload = insight_input.model_dump(mode="json", exclude={"inputs_hash"})
    return _hash_payload(payload)


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class _EvidenceScope:
    application_statuses: tuple[ApplicationStatus, ...] = ()
    event_types: tuple[ApplicationEventType, ...] = ()
    newest_first: bool = False


def _evidence_scope(insight_type: InsightType) -> _EvidenceScope:
    if insight_type in {"why_rejected", "skill_gaps"}:
        return _EvidenceScope(event_types=("rejection", "feedback"))
    if insight_type == "role_fit":
        return _EvidenceScope(application_statuses=("interview", "offer", "rejected", "ghosted"))
    if insight_type == "weekly_actions":
        return _EvidenceScope(
            application_statuses=("applied", "in_review", "assessment", "interview"),
            newest_first=True,
        )
    return _EvidenceScope()
