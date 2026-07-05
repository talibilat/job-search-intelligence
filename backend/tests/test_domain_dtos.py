from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app import models
from pydantic import ValidationError

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
EMBEDDING_1536 = tuple(0.0 for _ in range(1536))


def test_domain_dtos_are_exported_from_model_package() -> None:
    expected_model_names = [
        "RawEmailRecord",
        "EmailClassificationRecord",
        "ClassificationRunRecord",
        "ApplicationRecord",
        "ApplicationEventRecord",
        "InsightRecord",
        "EmailChunkRecord",
        "ApplicationCorrectionRecord",
    ]

    for name in expected_model_names:
        assert isinstance(getattr(models, name, None), type), name


def test_email_classification_record_validates_category_and_confidence() -> None:
    classification = models.EmailClassificationRecord(
        email_id="email-1",
        is_job_related=True,
        category=models.JobEmailCategory.APPLICATION_CONFIRMATION,
        confidence=0.96,
        model="synthetic-classifier",
        prompt_version="prompt-v1",
        classified_at=NOW,
    )

    assert classification.category is models.JobEmailCategory.APPLICATION_CONFIRMATION

    with pytest.raises(ValidationError):
        models.EmailClassificationRecord.model_validate(
            {
                "email_id": "email-1",
                "is_job_related": True,
                "category": "not_a_real_category",
                "confidence": 0.96,
                "model": "synthetic-classifier",
                "prompt_version": "prompt-v1",
                "classified_at": NOW,
            },
        )

    with pytest.raises(ValidationError):
        models.EmailClassificationRecord(
            email_id="email-1",
            is_job_related=True,
            category=models.JobEmailCategory.APPLICATION_CONFIRMATION,
            confidence=1.01,
            model="synthetic-classifier",
            prompt_version="prompt-v1",
            classified_at=NOW,
        )


def test_classification_run_record_validates_token_usage_and_estimated_cost() -> None:
    run = models.ClassificationRunRecord(
        id="classification-run-1",
        provider="azure_openai",
        model="gpt-4.1-mini",
        prompt_version="prompt-v1",
        started_at=NOW,
        completed_at=NOW,
        candidate_count=3,
        classified_count=3,
        prompt_tokens=120,
        completion_tokens=30,
        total_tokens=150,
        estimated_cost_usd=Decimal("0.000450"),
    )

    assert run.total_tokens == 150
    assert run.estimated_cost_usd == Decimal("0.000450")

    with pytest.raises(ValidationError, match="classified_count cannot exceed candidate_count"):
        models.ClassificationRunRecord.model_validate(
            run.model_dump() | {"classified_count": 4},
        )

    with pytest.raises(ValidationError, match="total_tokens cannot be less"):
        models.ClassificationRunRecord.model_validate(
            run.model_dump() | {"total_tokens": 149},
        )

    with pytest.raises(ValidationError):
        models.ClassificationRunRecord.model_validate(
            run.model_dump() | {"estimated_cost_usd": Decimal("-0.000001")},
        )


def test_application_record_rejects_inverted_salary_range() -> None:
    base_data = {
        "id": "application-1",
        "company": "Example Systems",
        "role_title": "Backend Engineer",
        "source": "company_site",
        "first_seen_at": NOW,
        "current_status": "applied",
        "currency": "USD",
        "location": "Remote",
        "work_mode": "remote",
        "seniority": "senior",
        "sponsorship": "unknown",
        "tech_stack": ["Python", "FastAPI"],
        "last_activity_at": NOW,
        "manual_lock": False,
        "created_at": NOW,
        "updated_at": NOW,
    }

    with pytest.raises(
        ValidationError,
        match="salary_min must be less than or equal to salary_max",
    ):
        models.ApplicationRecord.model_validate(
            base_data | {"salary_min": 150_000, "salary_max": 120_000},
        )


def test_email_chunk_record_validates_embedding_shape_and_hides_content_from_repr() -> None:
    chunk = models.EmailChunkRecord(
        email_id="email-1",
        chunk_index=0,
        content="Private retained email chunk text.",
        embedding=EMBEDDING_1536,
    )

    assert chunk.embedding == EMBEDDING_1536
    assert "Private retained email chunk text" not in repr(chunk)

    with pytest.raises(ValidationError, match="email chunk embeddings must have 1536 dimensions"):
        models.EmailChunkRecord(
            email_id="email-1",
            chunk_index=0,
            content="Private retained email chunk text.",
            embedding=(0.0, 1.0),
        )


def test_application_correction_record_parses_json_object_columns() -> None:
    correction = models.ApplicationCorrectionRecord.model_validate(
        {
            "id": 1,
            "application_id": "application-1",
            "correction_type": "status_edit",
            "before_json": '{"current_status":"applied"}',
            "after_json": '{"current_status":"rejected"}',
            "reason": "Manual audit after inbox spot check.",
            "created_at": NOW,
        },
    )

    assert correction.before_json == {"current_status": "applied"}
    assert correction.after_json == {"current_status": "rejected"}


def test_chat_message_record_validates_role_and_json_array_columns() -> None:
    message = models.ChatMessageRecord.model_validate(
        {
            "id": 1,
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "You have one overdue follow-up.",
            "citations_json": '[{"email_id":"email-1"}]',
            "tool_outputs_json": '[{"tool":"structured_query"}]',
            "created_at": NOW,
        },
    )

    assert message.role == "assistant"
    assert message.citations_json == [{"email_id": "email-1"}]
    assert message.tool_outputs_json == [{"tool": "structured_query"}]

    with pytest.raises(ValidationError):
        models.ChatMessageRecord.model_validate(
            {
                "id": 1,
                "conversation_id": "conversation-1",
                "role": "sql_writer",
                "content": "You have one overdue follow-up.",
                "citations_json": "[]",
                "tool_outputs_json": "[]",
                "created_at": NOW,
            },
        )
