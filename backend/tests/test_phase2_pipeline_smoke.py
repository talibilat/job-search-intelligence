from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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
)
from app.models import (
    EmailFilterDecisionOutcome,
    EmailFilterDecisionRecord,
    RawEmailRecord,
    SyntheticApplication,
    SyntheticApplicationEvent,
    SyntheticEmailClassification,
    SyntheticFixtureFile,
    SyntheticRawEmail,
)
from app.pipeline.filter import build_broad_candidate_query
from app.providers.email import EmailAccountRef, EmailAddress, EmailMessageMetadata, EmailMessageRef
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMTokenUsage,
)
from app.services.aggregation import AggregationService
from app.services.structured_extraction import StructuredExtractionService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = BACKEND_ROOT / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"
NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def test_phase2_pipeline_smoke_runs_filter_classify_extract_and_aggregate(
    tmp_path: Path,
) -> None:
    fixture = load_fixture()
    connection = migrated_connection(tmp_path)
    smoke_emails = (*fixture.emails, non_candidate_email())
    email_repository = EmailRepository(connection)
    email_repository.upsert_raw_emails(raw_email_records(smoke_emails))

    filter_decisions = evaluate_filter_decisions(smoke_emails)
    EmailFilterDecisionRepository(connection).upsert_filter_decisions(filter_decisions)
    candidate_decisions = [
        decision
        for decision in filter_decisions
        if decision.outcome is EmailFilterDecisionOutcome.CANDIDATE
    ]
    rejected_decisions = [
        decision
        for decision in filter_decisions
        if decision.outcome is EmailFilterDecisionOutcome.REJECTED
    ]

    assert [decision.email_id for decision in candidate_decisions] == [
        classification.email_id for classification in fixture.classifications
    ]
    assert [(decision.email_id, decision.reason) for decision in rejected_decisions] == [
        ("email-newsletter", "no_filter_signal"),
    ]

    llm_provider = FixtureLLMProvider(
        responses_by_email_id=classification_responses_by_email_id(fixture),
    )
    classification_run_repository = ClassificationRunRepository(connection)
    extraction_result = asyncio.run(
        StructuredExtractionService(
            settings=AppSettings(
                _env_file=None,
                classification_mode=ClassificationMode.LOCAL,
                llm_provider=LLMProviderName.OLLAMA,
                ollama_chat_model="phase2-smoke-model",
                classification_prompt_version="phase2-smoke-v1",
                classification_batch_size=10,
            ),
            email_repository=email_repository,
            classification_run_repository=classification_run_repository,
            llm_provider=llm_provider,
            clock=lambda: NOW,
            run_id_factory=lambda: "phase2-smoke-run",
        ).run_batch(),
    )

    assert [request_email_id(request) for request in llm_provider.requests] == [
        classification.email_id for classification in fixture.classifications
    ]
    assert extraction_result.run_record.candidate_count == len(fixture.classifications)
    assert extraction_result.run_record.classified_count == len(fixture.classifications)
    assert extraction_result.malformed_results == ()
    stored_run = classification_run_repository.fetch_run("phase2-smoke-run")
    assert stored_run is not None
    assert stored_run.provider == "ollama"
    assert stored_run.model == "phase2-smoke-model"
    assert stored_run.prompt_version == "phase2-smoke-v1"
    assert stored_run.candidate_count == len(fixture.classifications)
    assert stored_run.classified_count == len(fixture.classifications)
    assert stored_run.prompt_tokens == 10 * len(fixture.classifications)
    assert stored_run.completion_tokens == 5 * len(fixture.classifications)
    assert stored_run.total_tokens == 15 * len(fixture.classifications)
    assert stored_run.estimated_cost_usd == Decimal("0")

    aggregation_service = AggregationService(
        application_repository=ApplicationRepository(connection),
        event_repository=EventRepository(connection),
        email_repository=email_repository,
        correction_conflict_repository=CorrectionConflictRepository(connection),
        clock=lambda: NOW,
        run_id_factory=lambda: "phase2-smoke-aggregation-run",
    )
    first_aggregation = aggregation_service.run(list(extraction_result.accepted_results))
    second_aggregation = aggregation_service.run(list(extraction_result.accepted_results))

    assert first_aggregation.extraction_count == len(fixture.classifications)
    assert first_aggregation.applications_upserted == 1
    assert first_aggregation.events_upserted == 2
    assert second_aggregation.extraction_count == len(fixture.classifications)
    assert count_rows(connection, "applications") == 1
    assert count_rows(connection, "application_events") == 2
    assert count_rows(connection, "email_classifications") == len(fixture.classifications)
    assert count_rows(connection, "email_filter_decisions") == len(smoke_emails)

    stored_application = connection.execute(
        """
        SELECT company, role_title, current_status, salary_min, salary_max,
            currency, location, work_mode, seniority, sponsorship, tech_stack
        FROM applications
        """,
    ).fetchone()
    assert tuple(stored_application) == (
        "Example Systems",
        "Backend Engineer",
        "rejected",
        120000,
        150000,
        "USD",
        "Remote",
        "remote",
        "senior",
        "unknown",
        '["Python","FastAPI"]',
    )

    stored_events = connection.execute(
        """
        SELECT event_type, email_id, event_at, extract_note, extracted_status
        FROM application_events
        ORDER BY event_at
        """,
    ).fetchall()
    assert [tuple(row) for row in stored_events] == [
        (
            "applied",
            "email-application-confirmation",
            "2026-07-04T12:00:00+00:00",
            None,
            "applied",
        ),
        (
            "rejection",
            "email-rejection",
            "2026-07-18T15:30:00+00:00",
            "Rejection received after review.",
            "rejected",
        ),
    ]


class FixtureLLMProvider:
    provider_name = "ollama"

    def __init__(self, *, responses_by_email_id: dict[str, dict[str, Any]]) -> None:
        self._responses_by_email_id = responses_by_email_id
        self.requests: list[LLMGenerationRequest] = []

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        self.requests.append(request)
        email_id = request_email_id(request)
        return LLMGenerationResponse(
            content=json.dumps(
                self._responses_by_email_id[email_id],
                separators=(",", ":"),
            ),
            model="phase2-smoke-model",
            finish_reason=LLMFinishReason.STOP,
            usage=LLMTokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def health_check(
        self,
        request: LLMProviderHealthCheckRequest,
    ) -> LLMProviderHealthCheckResponse:
        raise NotImplementedError


def load_fixture() -> SyntheticFixtureFile:
    return SyntheticFixtureFile.model_validate(json.loads(FIXTURE_PATH.read_text()))


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def raw_email_records(emails: tuple[SyntheticRawEmail, ...]) -> tuple[RawEmailRecord, ...]:
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


def non_candidate_email() -> SyntheticRawEmail:
    return SyntheticRawEmail(
        id="email-newsletter",
        provider=EmailProviderName.GMAIL,
        thread_id="thread-newsletter",
        from_addr="news@example.test",
        to_addr="jobseeker@example.test",
        subject="Weekly account digest",
        sent_at=datetime(2026, 7, 17, 9, 0, tzinfo=UTC),
        ingested_at=NOW,
        labels=("INBOX",),
    )


def evaluate_filter_decisions(
    emails: tuple[SyntheticRawEmail, ...],
) -> list[EmailFilterDecisionRecord]:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="synthetic@example.test")
    metadata = tuple(metadata_from_email(email, account) for email in emails)
    query = build_broad_candidate_query()
    decisions = query.evaluate_metadata_batch(metadata)
    return [
        EmailFilterDecisionRecord(
            email_id=message.ref.message_id,
            strategy=decision.strategy,
            outcome=decision.outcome,
            reason=decision.reason,
            decided_at=NOW,
        )
        for message, decision in zip(metadata, decisions, strict=True)
    ]


def metadata_from_email(
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


def classification_responses_by_email_id(
    fixture: SyntheticFixtureFile,
) -> dict[str, dict[str, Any]]:
    applications_by_id = {application.id: application for application in fixture.applications}
    events_by_email_id = {
        event.email_id: event for event in fixture.events if event.email_id is not None
    }
    return {
        classification.email_id: classification_response(
            classification=classification,
            application=applications_by_id[events_by_email_id[classification.email_id].application_id],
            event=events_by_email_id[classification.email_id],
        )
        for classification in fixture.classifications
    }


def classification_response(
    *,
    classification: SyntheticEmailClassification,
    application: SyntheticApplication,
    event: SyntheticApplicationEvent,
) -> dict[str, Any]:
    return {
        "is_job_related": classification.is_job_related,
        "category": classification.category.value,
        "confidence": classification.confidence,
        "company": application.company,
        "role_title": application.role_title,
        "application_status": application_status_for_event(event),
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


def application_status_for_event(event: SyntheticApplicationEvent) -> str | None:
    return {
        "applied": "applied",
        "response": "in_review",
        "assessment": "assessment",
        "interview_scheduled": "interview",
        "feedback": None,
        "rejection": "rejected",
        "offer": "offer",
        "ghost_inferred": "ghosted",
    }[event.event_type.value]


def request_email_id(request: LLMGenerationRequest) -> str:
    payload = json.loads(request.messages[1].content)
    email_id = payload["email_id"]
    assert isinstance(email_id, str)
    return email_id


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    assert row is not None
    return int(row[0])
