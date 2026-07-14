from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from app.config import AppSettings, get_settings
from app.db.repositories import EmailRepository
from app.main import create_app
from app.models import (
    ClassificationCandidateStats,
    ClassificationRunRecord,
    EmailClassificationRecord,
    GhostInferenceRunResponse,
    JobEmailCategory,
    ProcessingRunRequest,
)
from app.pipeline.classify import (
    AcceptedLLMExtraction,
    JobApplicationExtraction,
    MalformedLLMExtraction,
    MalformedLLMExtractionReason,
)
from app.services.aggregation import AggregationRunResult
from app.services.processing import ProcessingOrchestrationService, build_processing_status
from app.services.structured_extraction import StructuredExtractionRunResult
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_processing_runs_multiple_batches_and_integrates_ghosts() -> None:
    extraction = _ExtractionService(
        [
            _batch("batch-1", accepted=(_accepted("email-1", is_job_related=True),)),
            _batch(
                "batch-2",
                accepted=(
                    _accepted("email-2", is_job_related=False),
                    _accepted("email-3", is_job_related=True),
                ),
            ),
            _batch("batch-empty"),
        ]
    )
    aggregation = _AggregationService()
    service = _service(
        pending_count=3,
        extraction=extraction,
        aggregation=aggregation,
        ghosts=_GhostService(updates=1, conflicts=2),
    )

    result = asyncio.run(service.run(ProcessingRunRequest()))

    assert result.processed_count == 3
    assert result.accepted_count == 3
    assert result.skipped_not_job_count == 1
    assert result.applications_upserted == 2
    assert result.events_upserted == 2
    assert result.ghost_updates == 1
    assert result.manual_conflict_count == 2
    assert result.prompt_tokens == 30
    assert result.total_tokens == 45
    assert len(extraction.calls) == 3


def test_processing_skips_malformed_candidate_within_run_and_honors_limit() -> None:
    extraction = _ExtractionService(
        [
            _batch("batch-1", malformed=(_malformed("bad-email"),)),
            _batch("batch-2", accepted=(_accepted("good-email", is_job_related=True),)),
        ]
    )
    service = _service(pending_count=4, extraction=extraction)

    result = asyncio.run(service.run(ProcessingRunRequest(max_candidates=2)))

    assert result.processed_count == 2
    assert result.malformed_count == 1
    assert result.accepted_count == 1
    assert result.limit_reached is True
    assert extraction.calls[1][1] == ("bad-email",)


def test_processing_zero_candidates_still_reconciles_ghosts() -> None:
    extraction = _ExtractionService([_batch("empty")])
    ghosts = _GhostService(updates=0, retractions=1)
    service = _service(pending_count=0, extraction=extraction, ghosts=ghosts)

    result = asyncio.run(service.run(ProcessingRunRequest()))

    assert result.processed_count == 0
    assert result.accepted_count == 0
    assert result.ghost_retractions == 1
    assert ghosts.calls == 1


def test_processing_rerun_reports_idempotent_upsert_outcomes() -> None:
    accepted = _accepted("email-1", is_job_related=True)
    aggregation = _AggregationService(idempotent=True)
    first = _service(
        pending_count=1,
        extraction=_ExtractionService([_batch("first", accepted=(accepted,))]),
        aggregation=aggregation,
    )
    second = _service(
        pending_count=1,
        extraction=_ExtractionService([_batch("second", accepted=(accepted,))]),
        aggregation=aggregation,
    )

    first_result = asyncio.run(first.run(ProcessingRunRequest(max_candidates=1)))
    second_result = asyncio.run(second.run(ProcessingRunRequest(max_candidates=1)))

    assert first_result.applications_upserted == 1
    assert first_result.events_upserted == 1
    assert second_result.applications_upserted == 0
    assert second_result.events_upserted == 0


def test_processing_status_reports_pending_model_and_safe_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO raw_emails (
                id, thread_id, from_addr, to_addr, subject, sent_at, body_text,
                body_retention_state, labels, provider, ingested_at
            ) VALUES (
                'email-1', 'thread-1', 'jobs@example.test', 'me@example.test',
                'Application', ?, 'Retained private content', 'retained', '[]', 'gmail', ?
            )
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        status = build_processing_status(
            settings=AppSettings(
                _env_file=None,
                processing_max_candidates_per_run=17,
                ollama_chat_model="local-model",
                classification_prompt_version="v2",
            ),
            email_repository=EmailRepository(connection),
        )

    assert status.state == "idle"
    assert status.pending_candidate_count == 1
    assert status.candidate_limit == 17
    assert status.model == "local-model"
    assert status.prompt_version == "v2"
    assert "Retained private content" not in status.model_dump_json()


def test_processing_status_endpoint_exposes_typed_local_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        processing_max_candidates_per_run=23,
    )

    response = TestClient(app).get("/processing/status")

    assert response.status_code == 200
    assert response.json()["state"] == "idle"
    assert response.json()["candidate_limit"] == 23
    assert response.json()["pending_candidate_count"] == 0


class _CandidateRepository:
    def __init__(self, pending_count: int) -> None:
        self.pending_count = pending_count

    def get_classification_candidate_stats(self, **_: Any) -> ClassificationCandidateStats:
        return ClassificationCandidateStats(
            candidate_count=self.pending_count,
            body_text_char_count=0,
        )


class _ExtractionService:
    def __init__(self, batches: list[StructuredExtractionRunResult]) -> None:
        self.batches = list(batches)
        self.calls: list[tuple[int | None, tuple[str, ...]]] = []

    async def run_batch(
        self,
        *,
        limit: int | None = None,
        excluded_email_ids: tuple[str, ...] = (),
    ) -> StructuredExtractionRunResult:
        self.calls.append((limit, excluded_email_ids))
        return self.batches.pop(0)


class _AggregationService:
    def __init__(self, *, idempotent: bool = False) -> None:
        self.idempotent = idempotent
        self.seen: set[str] = set()

    def run(self, accepted: list[AcceptedLLMExtraction]) -> AggregationRunResult:
        job_ids = [
            item.classification.email_id for item in accepted if item.classification.is_job_related
        ]
        new_ids = [email_id for email_id in job_ids if email_id not in self.seen]
        self.seen.update(new_ids)
        count = len(new_ids) if self.idempotent else len(job_ids)
        return AggregationRunResult(
            run_id="aggregation",
            started_at=NOW,
            completed_at=NOW,
            extraction_count=len(accepted),
            applications_upserted=count,
            events_upserted=count,
            skipped_not_job_related=len(accepted) - len(job_ids),
        )


class _GhostService:
    def __init__(
        self,
        *,
        updates: int = 0,
        retractions: int = 0,
        conflicts: int = 0,
    ) -> None:
        self.updates = updates
        self.retractions = retractions
        self.conflicts = conflicts
        self.calls = 0

    def run(self) -> GhostInferenceRunResponse:
        self.calls += 1
        return GhostInferenceRunResponse(
            evaluated_at=NOW,
            threshold_days=30,
            applications_ghosted=self.updates,
            ghosted_application_ids=[f"ghost-{index}" for index in range(self.updates)],
            ghost_retraction_count=self.retractions,
            retracted_application_ids=[f"retracted-{index}" for index in range(self.retractions)],
            manual_conflict_count=self.conflicts,
            manual_conflict_application_ids=[
                f"conflict-{index}" for index in range(self.conflicts)
            ],
        )


def _service(
    *,
    pending_count: int,
    extraction: _ExtractionService,
    aggregation: _AggregationService | None = None,
    ghosts: _GhostService | None = None,
) -> ProcessingOrchestrationService:
    return ProcessingOrchestrationService(
        settings=AppSettings(
            _env_file=None,
            classification_batch_size=2,
            processing_max_candidates_per_run=10,
            ollama_chat_model="local-model",
            classification_prompt_version="v2",
        ),
        email_repository=_CandidateRepository(pending_count),  # type: ignore[arg-type]
        extraction_service=extraction,  # type: ignore[arg-type]
        aggregation_service=aggregation or _AggregationService(),  # type: ignore[arg-type]
        ghost_inference_service=ghosts or _GhostService(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        run_id_factory=lambda: "processing-run",
    )


def _batch(
    run_id: str,
    *,
    accepted: tuple[AcceptedLLMExtraction, ...] = (),
    malformed: tuple[MalformedLLMExtraction, ...] = (),
) -> StructuredExtractionRunResult:
    candidate_count = len(accepted) + len(malformed)
    return StructuredExtractionRunResult(
        run_record=ClassificationRunRecord(
            id=run_id,
            provider="ollama",
            model="local-model",
            prompt_version="v2",
            started_at=NOW,
            completed_at=NOW,
            candidate_count=candidate_count,
            classified_count=len(accepted),
            prompt_tokens=candidate_count * 10,
            completion_tokens=candidate_count * 5,
            total_tokens=candidate_count * 15,
            estimated_cost_usd=Decimal("0"),
        ),
        accepted_results=accepted,
        malformed_results=malformed,
    )


def _accepted(email_id: str, *, is_job_related: bool) -> AcceptedLLMExtraction:
    return AcceptedLLMExtraction(
        classification=EmailClassificationRecord(
            email_id=email_id,
            is_job_related=is_job_related,
            category=(
                JobEmailCategory.APPLICATION_CONFIRMATION
                if is_job_related
                else JobEmailCategory.OTHER
            ),
            confidence=0.9,
            model="local-model",
            prompt_version="v2",
            classified_at=NOW,
        ),
        extraction=JobApplicationExtraction(
            company="Example" if is_job_related else None,
            role_title="Engineer" if is_job_related else None,
            status="applied" if is_job_related else None,
            event_type="applied" if is_job_related else None,
            event_at=NOW if is_job_related else None,
            sponsorship="unknown",
        ),
    )


def _malformed(email_id: str) -> MalformedLLMExtraction:
    return MalformedLLMExtraction(
        email_id=email_id,
        model="local-model",
        prompt_version="v2",
        reason=MalformedLLMExtractionReason.INVALID_JSON,
        message="The provider returned malformed structured output.",
    )
