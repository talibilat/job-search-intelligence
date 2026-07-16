from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.config import AppSettings
from app.db.repositories import EmailRepository
from app.models import (
    ProcessingRunRequest,
    ProcessingRunResult,
    ProcessingRunState,
    ProcessingStatus,
)
from app.services.aggregation import AggregationService
from app.services.classification_target import resolve_classification_model
from app.services.ghost_inference import GhostInferenceService
from app.services.structured_extraction import StructuredExtractionService

type Clock = Callable[[], datetime]
type RunIdFactory = Callable[[], str]
type StatusCallback = Callable[[ProcessingStatus], None]


class ProcessingOrchestrationService:
    """Run bounded classification batches followed by aggregation and ghost inference."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        email_repository: EmailRepository,
        extraction_service: StructuredExtractionService,
        aggregation_service: AggregationService,
        ghost_inference_service: GhostInferenceService,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory | None = None,
    ) -> None:
        self._settings = settings
        self._email_repository = email_repository
        self._extraction_service = extraction_service
        self._aggregation_service = aggregation_service
        self._ghost_inference_service = ghost_inference_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._run_id_factory = run_id_factory or (lambda: uuid4().hex)

    def status(self) -> ProcessingStatus:
        return build_processing_status(
            settings=self._settings,
            email_repository=self._email_repository,
        )

    async def run(
        self,
        request: ProcessingRunRequest,
        *,
        status_callback: StatusCallback | None = None,
    ) -> ProcessingRunResult:
        started_at = self._clock()
        run_id = self._run_id_factory()
        pending_count = self._pending_count()
        candidate_limit = min(
            request.max_candidates or self._settings.processing_max_candidates_per_run,
            self._settings.processing_max_candidates_per_run,
        )
        attempted_email_ids: list[str] = []
        accepted_count = malformed_count = skipped_not_job_count = 0
        applications_upserted = events_upserted = manual_conflict_count = 0
        prompt_tokens = completion_tokens = total_tokens = 0
        estimated_cost_usd = 0.0

        if status_callback is not None:
            status_callback(
                self._empty_status(
                    state=ProcessingRunState.RUNNING,
                    run_id=run_id,
                    started_at=started_at,
                    pending_candidate_count=pending_count,
                    candidate_limit=candidate_limit,
                )
            )

        while len(attempted_email_ids) < candidate_limit:
            remaining = candidate_limit - len(attempted_email_ids)
            batch = await self._extraction_service.run_batch(
                limit=min(self._settings.classification_batch_size, remaining),
                excluded_email_ids=tuple(attempted_email_ids),
            )
            if batch.run_record.candidate_count == 0:
                break

            batch_email_ids = [
                *(item.classification.email_id for item in batch.accepted_results),
                *(item.email_id for item in batch.malformed_results),
            ]
            attempted_email_ids.extend(batch_email_ids)
            accepted_count += len(batch.accepted_results)
            malformed_count += len(batch.malformed_results)
            prompt_tokens += batch.run_record.prompt_tokens
            completion_tokens += batch.run_record.completion_tokens
            total_tokens += batch.run_record.total_tokens
            estimated_cost_usd += float(batch.run_record.estimated_cost_usd)

            aggregation = self._aggregation_service.run(list(batch.accepted_results))
            skipped_not_job_count += aggregation.skipped_not_job_related
            applications_upserted += aggregation.applications_upserted
            events_upserted += aggregation.events_upserted
            manual_conflict_count += aggregation.manual_conflict_count
            if status_callback is not None:
                status_callback(
                    self._empty_status(
                        state=ProcessingRunState.RUNNING,
                        run_id=run_id,
                        started_at=started_at,
                        pending_candidate_count=self._pending_count(),
                        candidate_limit=candidate_limit,
                    ).model_copy(
                        update={
                            "processed_count": len(attempted_email_ids),
                            "accepted_count": accepted_count,
                            "malformed_count": malformed_count,
                            "skipped_not_job_count": skipped_not_job_count,
                            "applications_upserted": applications_upserted,
                            "events_upserted": events_upserted,
                            "manual_conflict_count": manual_conflict_count,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                            "estimated_cost_usd": estimated_cost_usd,
                        }
                    )
                )
            if not batch_email_ids:
                break

        ghosts = self._ghost_inference_service.run()
        manual_conflict_count += ghosts.manual_conflict_count
        result = ProcessingRunResult(
            state=ProcessingRunState.SUCCEEDED,
            run_id=run_id,
            started_at=started_at,
            completed_at=self._clock(),
            pending_candidate_count=self._pending_count(),
            candidate_count=pending_count,
            candidate_limit=candidate_limit,
            processed_count=len(attempted_email_ids),
            accepted_count=accepted_count,
            malformed_count=malformed_count,
            skipped_not_job_count=skipped_not_job_count,
            applications_upserted=applications_upserted,
            events_upserted=events_upserted,
            ghost_updates=ghosts.applications_ghosted,
            ghost_retractions=ghosts.ghost_retraction_count,
            manual_conflict_count=manual_conflict_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            model=resolve_classification_model(self._settings),
            prompt_version=self._settings.classification_prompt_version,
            llm_provider=self._settings.llm_provider,
            classification_mode=self._settings.classification_mode,
            limit_reached=(
                len(attempted_email_ids) >= candidate_limit
                and pending_count > len(attempted_email_ids)
            ),
        )
        if status_callback is not None:
            status_callback(result)
        return result

    def _pending_count(self) -> int:
        return self._email_repository.get_classification_candidate_stats(
            provider=self._settings.email_provider,
            model=resolve_classification_model(self._settings),
            prompt_version=self._settings.classification_prompt_version,
        ).candidate_count

    def _empty_status(
        self,
        *,
        state: ProcessingRunState,
        pending_candidate_count: int,
        candidate_limit: int,
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> ProcessingStatus:
        return ProcessingStatus(
            state=state,
            run_id=run_id,
            started_at=started_at,
            pending_candidate_count=pending_candidate_count,
            candidate_count=pending_candidate_count,
            candidate_limit=candidate_limit,
            processed_count=0,
            accepted_count=0,
            malformed_count=0,
            skipped_not_job_count=0,
            applications_upserted=0,
            events_upserted=0,
            ghost_updates=0,
            ghost_retractions=0,
            manual_conflict_count=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            estimated_cost_usd=0,
            model=resolve_classification_model(self._settings),
            prompt_version=self._settings.classification_prompt_version,
            llm_provider=self._settings.llm_provider,
            classification_mode=self._settings.classification_mode,
        )


def build_processing_status(
    *,
    settings: AppSettings,
    email_repository: EmailRepository,
) -> ProcessingStatus:
    pending_count = email_repository.get_classification_candidate_stats(
        provider=settings.email_provider,
        model=resolve_classification_model(settings),
        prompt_version=settings.classification_prompt_version,
    ).candidate_count
    return ProcessingStatus(
        state=ProcessingRunState.IDLE,
        pending_candidate_count=pending_count,
        candidate_count=pending_count,
        candidate_limit=settings.processing_max_candidates_per_run,
        processed_count=0,
        accepted_count=0,
        malformed_count=0,
        skipped_not_job_count=0,
        applications_upserted=0,
        events_upserted=0,
        ghost_updates=0,
        ghost_retractions=0,
        manual_conflict_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        estimated_cost_usd=0,
        model=resolve_classification_model(settings),
        prompt_version=settings.classification_prompt_version,
        llm_provider=settings.llm_provider,
        classification_mode=settings.classification_mode,
    )
