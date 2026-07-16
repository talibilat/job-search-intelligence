from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from alembic import command
from alembic.config import Config
from app.config import AppSettings, ClassificationMode, EmailProviderName, LLMProviderName
from app.db.repositories import (
    ApplicationRepository,
    ClassificationRunRepository,
    CorrectionConflictRepository,
    EmailFilterDecisionRepository,
    EmailRepository,
    EventRepository,
    MetricsRepository,
)
from app.models import (
    EmailFilterDecisionOutcome,
    EmailFilterDecisionRecord,
    RawEmailRecord,
    SyntheticEmailClassification,
    SyntheticFixtureFile,
    SyntheticRawEmail,
)
from app.models.synthetic_fixture import SyntheticApplication, SyntheticApplicationEvent
from app.pipeline.filter import build_broad_candidate_query
from app.providers.email import EmailAccountRef, EmailAddress, EmailMessageMetadata, EmailMessageRef
from app.providers.llm import (
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMTokenUsage,
)
from app.services.aggregation import AggregationService
from app.services.ghost_inference import GhostInferenceService
from app.services.metrics import MetricsSummaryService
from app.services.structured_extraction import StructuredExtractionService
from pydantic import BaseModel, ConfigDict, Field

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = (
    BACKEND_ROOT / "tests" / "fixtures" / "synthetic" / "diagnostic_job_search.json"
)
DIAGNOSTIC_NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
GHOST_THRESHOLD_DAYS = 30


class PipelineDiagnosticStage(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    count: int = Field(ge=0)
    expected: int = Field(ge=0)


class PipelineDiagnosticMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_applications: int = Field(ge=0)
    rejected_applications: int = Field(ge=0)
    ghosted_applications: int = Field(ge=0)
    interview_invitations: int = Field(ge=0)
    offers_received: int = Field(ge=0)
    human_responses: int = Field(ge=0)
    silent_applications: int = Field(ge=0)


class PipelineDiagnosticReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["passed"] = "passed"
    fixture_id: str = Field(min_length=1)
    stages: tuple[PipelineDiagnosticStage, ...]
    metrics: PipelineDiagnosticMetrics


class PipelineDiagnosticError(RuntimeError):
    def __init__(self, *, stage: str, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"pipeline diagnostic failed at {stage}: {detail}")


async def run_pipeline_diagnostic(
    *,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    database_path: Path,
) -> PipelineDiagnosticReport:
    fixture = _load_fixture(fixture_path)
    _migrate_database(database_path)

    with sqlite3.connect(database_path) as connection:
        email_repository = EmailRepository(connection)
        expected_candidate_ids = {item.email_id for item in fixture.classifications}
        stages: list[PipelineDiagnosticStage] = []

        email_repository.upsert_raw_emails(_raw_email_records(fixture.emails))
        stages.append(
            _checked_stage(
                "raw_emails",
                email_repository.count_raw_emails(),
                len(fixture.emails),
            )
        )

        decisions = _filter_decisions(fixture.emails)
        EmailFilterDecisionRepository(connection).upsert_filter_decisions(decisions)
        candidate_ids = {
            item.email_id
            for item in decisions
            if item.outcome is EmailFilterDecisionOutcome.CANDIDATE
        }
        if candidate_ids != expected_candidate_ids:
            raise PipelineDiagnosticError(
                stage="retained_candidates",
                detail=(
                    "filter candidates did not match the fixture classification set; "
                    f"expected {len(expected_candidate_ids)}, got {len(candidate_ids)}"
                ),
            )
        stages.append(
            _checked_stage(
                "retained_candidates",
                len(candidate_ids),
                len(expected_candidate_ids),
            )
        )

        settings = AppSettings(
            _env_file=None,
            classification_mode=ClassificationMode.LOCAL,
            llm_provider=LLMProviderName.OLLAMA,
            ollama_chat_model="pipeline-diagnostic-model",
            classification_prompt_version="pipeline-diagnostic-v1",
            classification_batch_size=max(1, len(expected_candidate_ids)),
        )
        extraction_result = await StructuredExtractionService(
            settings=settings,
            email_repository=email_repository,
            classification_run_repository=ClassificationRunRepository(connection),
            llm_provider=_FixtureLLMProvider(
                responses_by_email_id=_classification_responses(fixture),
            ),
            clock=lambda: DIAGNOSTIC_NOW,
            run_id_factory=lambda: "pipeline-diagnostic-classification",
        ).run_batch()
        if extraction_result.malformed_results:
            malformed_count = len(extraction_result.malformed_results)
            raise PipelineDiagnosticError(
                stage="classifications",
                detail=f"{malformed_count} fixture responses were malformed",
            )
        classification_count = _count_rows(connection, "email_classifications")
        stages.append(
            _checked_stage(
                "classifications",
                classification_count,
                len(fixture.classifications),
            )
        )

        aggregation_result = AggregationService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            email_repository=email_repository,
            correction_conflict_repository=CorrectionConflictRepository(connection),
            clock=lambda: DIAGNOSTIC_NOW,
            run_id_factory=lambda: "pipeline-diagnostic-aggregation",
        ).run(list(extraction_result.accepted_results))
        if aggregation_result.manual_conflict_count:
            raise PipelineDiagnosticError(
                stage="applications",
                detail=f"aggregation produced {aggregation_result.manual_conflict_count} conflicts",
            )
        stages.append(
            _checked_stage(
                "applications",
                _count_rows(connection, "applications"),
                len(fixture.applications),
            )
        )

        GhostInferenceService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            threshold_days=GHOST_THRESHOLD_DAYS,
            clock=lambda: DIAGNOSTIC_NOW,
        ).run()
        stages.append(
            _checked_stage(
                "application_events",
                _count_rows(connection, "application_events"),
                len(fixture.events),
            )
        )

        metrics_repository = MetricsRepository(connection)
        summary = MetricsSummaryService(
            metrics_repository=metrics_repository,
            ghost_threshold_days=GHOST_THRESHOLD_DAYS,
            clock=lambda: DIAGNOSTIC_NOW,
        ).get_summary()
        response_silence = metrics_repository.get_response_silence_metric()
        expected_rejections = sum(
            application.current_status.value == "rejected" for application in fixture.applications
        )
        stages.append(
            _checked_stage(
                "rejections",
                summary.rejected_applications,
                expected_rejections,
            )
        )
        _check_metric("total_applications", summary.total_applications, len(fixture.applications))
        _check_metric(
            "ghosted_applications",
            summary.ghosted_applications,
            sum(
                application.current_status.value == "ghosted"
                for application in fixture.applications
            ),
        )
        _check_metric(
            "interview_invitations",
            summary.interview_invitation_count,
            sum(event.event_type.value == "interview_scheduled" for event in fixture.events),
        )
        _check_metric(
            "offers_received",
            summary.offers_received,
            len(
                {
                    event.application_id
                    for event in fixture.events
                    if event.event_type.value == "offer"
                }
            ),
        )

        return PipelineDiagnosticReport(
            fixture_id=fixture.fixture_id,
            stages=tuple(stages),
            metrics=PipelineDiagnosticMetrics(
                total_applications=summary.total_applications,
                rejected_applications=summary.rejected_applications,
                ghosted_applications=summary.ghosted_applications,
                interview_invitations=summary.interview_invitation_count,
                offers_received=summary.offers_received,
                human_responses=response_silence.human_response_count,
                silent_applications=response_silence.silent_count,
            ),
        )


class _FixtureLLMProvider:
    provider_name = "ollama"

    def __init__(self, *, responses_by_email_id: dict[str, dict[str, Any]]) -> None:
        self._responses_by_email_id = responses_by_email_id

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        email_id = _request_email_id(request)
        response = self._responses_by_email_id.get(email_id)
        if response is None:
            raise PipelineDiagnosticError(
                stage="classifications",
                detail=f"fixture response missing for synthetic email {email_id}",
            )
        return LLMGenerationResponse(
            content=json.dumps(response, separators=(",", ":")),
            model="pipeline-diagnostic-model",
            finish_reason=LLMFinishReason.STOP,
            usage=LLMTokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def embed(self, request: LLMEmbeddingRequest) -> LLMEmbeddingResponse:
        raise NotImplementedError

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        raise NotImplementedError


def _load_fixture(path: Path) -> SyntheticFixtureFile:
    try:
        return SyntheticFixtureFile.model_validate(json.loads(path.read_text()))
    except Exception as error:
        raise PipelineDiagnosticError(stage="fixture", detail=str(error)) from error


def _migrate_database(database_path: Path) -> None:
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
        command.upgrade(config, "head")
    except Exception as error:
        raise PipelineDiagnosticError(stage="database", detail=str(error)) from error


def _raw_email_records(emails: tuple[SyntheticRawEmail, ...]) -> tuple[RawEmailRecord, ...]:
    return tuple(
        RawEmailRecord(
            id=email.id,
            thread_id=email.thread_id,
            from_addr=email.from_addr,
            to_addr=email.to_addr,
            subject=email.subject,
            sent_at=email.sent_at,
            body_text=email.body_text,
            body_retention_state=email.body_retention_state,
            labels=list(email.labels),
            provider=email.provider.value,
            ingested_at=email.ingested_at,
        )
        for email in emails
    )


def _filter_decisions(
    emails: tuple[SyntheticRawEmail, ...],
) -> tuple[EmailFilterDecisionRecord, ...]:
    account = EmailAccountRef(
        provider=EmailProviderName.GMAIL,
        account_id="pipeline-diagnostic@example.test",
    )
    metadata = tuple(_metadata_from_email(email, account) for email in emails)
    decisions = build_broad_candidate_query().evaluate_metadata_batch(metadata)
    return tuple(
        EmailFilterDecisionRecord(
            email_id=message.ref.message_id,
            strategy=decision.strategy,
            outcome=decision.outcome,
            reason=decision.reason,
            decided_at=DIAGNOSTIC_NOW,
        )
        for message, decision in zip(metadata, decisions, strict=True)
    )


def _metadata_from_email(
    email: SyntheticRawEmail,
    account: EmailAccountRef,
) -> EmailMessageMetadata:
    return EmailMessageMetadata(
        ref=EmailMessageRef(
            account=account,
            message_id=email.id,
            thread_id=email.thread_id,
        ),
        from_addr=EmailAddress(address=email.from_addr) if email.from_addr is not None else None,
        subject=email.subject,
        sent_at=email.sent_at,
        labels=email.labels,
    )


def _classification_responses(fixture: SyntheticFixtureFile) -> dict[str, dict[str, Any]]:
    applications = {application.id: application for application in fixture.applications}
    events = {event.email_id: event for event in fixture.events if event.email_id is not None}
    responses: dict[str, dict[str, Any]] = {}
    for classification in fixture.classifications:
        event = events.get(classification.email_id)
        if event is None or event.application_id not in applications:
            raise PipelineDiagnosticError(
                stage="fixture",
                detail=f"classification mapping missing for {classification.email_id}",
            )
        responses[classification.email_id] = _classification_response(
            classification=classification,
            application=applications[event.application_id],
            event=event,
        )
    return responses


def _classification_response(
    *,
    classification: SyntheticEmailClassification,
    application: SyntheticApplication,
    event: SyntheticApplicationEvent,
) -> dict[str, Any]:
    status_by_event = {
        "applied": "applied",
        "response": "in_review",
        "assessment": "assessment",
        "interview_scheduled": "interview",
        "feedback": None,
        "rejection": "rejected",
        "offer": "offer",
        "ghost_inferred": "ghosted",
    }
    return {
        "is_job_related": classification.is_job_related,
        "category": classification.category.value,
        "confidence": classification.confidence,
        "company": application.company,
        "role_title": application.role_title,
        "application_status": status_by_event[event.event_type.value],
        "event_type": event.event_type.value,
        "event_at": event.event_at.isoformat(),
        "salary_min": application.salary_min,
        "salary_max": application.salary_max,
        "currency": application.currency,
        "location": application.location,
        "work_mode": application.work_mode.value if application.work_mode is not None else None,
        "seniority": application.seniority,
        "sponsorship": application.sponsorship.value,
        "tech_stack": list(application.tech_stack),
        "rejection_reason": event.extract_note if event.event_type.value == "rejection" else None,
    }


def _request_email_id(request: LLMGenerationRequest) -> str:
    payload = json.loads(request.messages[1].content)
    email_id = payload.get("email_id")
    if not isinstance(email_id, str):
        raise PipelineDiagnosticError(
            stage="classifications",
            detail="classification request omitted its synthetic email id",
        )
    return email_id


def _checked_stage(name: str, count: int, expected: int) -> PipelineDiagnosticStage:
    if count != expected:
        raise PipelineDiagnosticError(
            stage=name,
            detail=f"expected {expected} rows, got {count}",
        )
    return PipelineDiagnosticStage(name=name, count=count, expected=expected)


def _check_metric(name: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise PipelineDiagnosticError(
            stage="metrics",
            detail=f"{name} expected {expected}, got {actual}",
        )


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    if row is None:
        return 0
    return int(row[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline synthetic email-to-metrics diagnostic.",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    args = parser.parse_args(argv)

    try:
        with tempfile.TemporaryDirectory(prefix="jobtracker-diagnostic-") as directory:
            report = asyncio.run(
                run_pipeline_diagnostic(
                    fixture_path=args.fixture,
                    database_path=Path(directory) / "jobtracker.sqlite3",
                )
            )
    except PipelineDiagnosticError as error:
        print(f"FAIL stage={error.stage}: {error.detail}", file=sys.stderr)
        return 1

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
