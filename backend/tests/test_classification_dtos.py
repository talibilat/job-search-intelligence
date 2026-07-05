from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app import models
from pydantic import ValidationError

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_classification_dtos_are_exported_from_model_package() -> None:
    expected_model_names = [
        "EmailClassificationCandidate",
        "EmailClassificationResult",
        "EmailClassificationRecord",
        "JobEmailCategory",
    ]

    for name in expected_model_names:
        assert isinstance(getattr(models, name, None), type), name


def test_classification_candidate_hides_retained_body_text_and_validates_timestamp() -> None:
    candidate = models.EmailClassificationCandidate(
        email_id="email-1",
        subject="Application received",
        from_addr="no-reply@ats.example",
        sent_at=NOW,
        body_text="Thank you for applying to Example Systems.",
    )

    assert candidate.email_id == "email-1"
    assert candidate.sent_at == NOW
    assert "Thank you for applying" not in repr(candidate)

    with pytest.raises(ValidationError, match="sent_at must be timezone-aware"):
        models.EmailClassificationCandidate(
            email_id="email-1",
            subject="Application received",
            from_addr="no-reply@ats.example",
            sent_at=datetime(2026, 7, 5, 12, 0),
            body_text="Thank you for applying to Example Systems.",
        )


def test_classification_result_validates_category_confidence_and_metadata() -> None:
    result = models.EmailClassificationResult(
        is_job_related=True,
        category=models.JobEmailCategory.APPLICATION_CONFIRMATION,
        confidence=0.96,
        model=" synthetic-classifier ",
        prompt_version=" prompt-v1 ",
        classified_at=NOW,
    )

    assert result.category is models.JobEmailCategory.APPLICATION_CONFIRMATION
    assert result.model == "synthetic-classifier"
    assert result.prompt_version == "prompt-v1"

    invalid_payload = {
        "is_job_related": True,
        "category": "application_confirmation",
        "confidence": 0.96,
        "model": "synthetic-classifier",
        "prompt_version": "prompt-v1",
        "classified_at": NOW,
    }

    with pytest.raises(ValidationError):
        models.EmailClassificationResult.model_validate(
            invalid_payload | {"category": "not_a_real_category"},
        )

    with pytest.raises(ValidationError):
        models.EmailClassificationResult.model_validate(
            invalid_payload | {"confidence": 1.01},
        )

    with pytest.raises(ValidationError):
        models.EmailClassificationResult.model_validate(
            invalid_payload | {"model": "   "},
        )

    with pytest.raises(ValidationError):
        models.EmailClassificationResult.model_validate(
            invalid_payload | {"prompt_version": "   "},
        )

    with pytest.raises(ValidationError, match="classified_at must be timezone-aware"):
        models.EmailClassificationResult.model_validate(
            invalid_payload | {"classified_at": datetime(2026, 7, 5, 12, 0)},
        )

    with pytest.raises(ValidationError):
        models.EmailClassificationResult.model_validate(
            invalid_payload | {"raw_provider_payload": {"private": "data"}},
        )


def test_classification_record_reuses_result_validation_with_email_id() -> None:
    record = models.EmailClassificationRecord(
        email_id="email-1",
        is_job_related=True,
        category=models.JobEmailCategory.REJECTION,
        confidence=0.88,
        model="synthetic-classifier",
        prompt_version="prompt-v1",
        classified_at=NOW,
    )

    assert record.email_id == "email-1"
    assert record.category is models.JobEmailCategory.REJECTION

    with pytest.raises(ValidationError, match="classified_at must be timezone-aware"):
        models.EmailClassificationRecord(
            email_id="email-1",
            is_job_related=True,
            category=models.JobEmailCategory.REJECTION,
            confidence=0.88,
            model="synthetic-classifier",
            prompt_version="prompt-v1",
            classified_at=datetime(2026, 7, 5, 12, 0),
        )
