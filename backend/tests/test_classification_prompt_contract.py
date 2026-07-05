from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from app import models
from app.pipeline.classify import (
    CLASSIFICATION_PROMPT_VERSION,
    ClassificationPromptEmail,
    build_classification_prompt_request,
    parse_classification_prompt_output,
)
from app.providers.llm import LLMMessageRole, LLMResponseFormat
from pydantic import ValidationError

SENT_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_classification_prompt_request_is_versioned_json_contract() -> None:
    email = ClassificationPromptEmail(
        email_id="email-1",
        from_addr="jobs@example.com",
        subject="Your application to Example Systems",
        sent_at=SENT_AT,
        body_text="Thanks for applying to the Backend Engineer role.",
    )

    request = build_classification_prompt_request(
        email,
        model="synthetic-classifier",
    )

    assert request.model == "synthetic-classifier"
    assert request.response_format is LLMResponseFormat.JSON_OBJECT
    assert request.options.temperature == 0
    assert len(request.messages) == 2
    assert request.messages[0].role is LLMMessageRole.SYSTEM
    assert f"Prompt version: {CLASSIFICATION_PROMPT_VERSION}" in request.messages[0].content
    assert "is_job_related" in request.messages[0].content
    assert "rejection_reason" in request.messages[0].content

    assert request.messages[1].role is LLMMessageRole.USER
    payload = json.loads(request.messages[1].content)
    assert payload == {
        "email_id": "email-1",
        "from_addr": "jobs@example.com",
        "subject": "Your application to Example Systems",
        "sent_at": "2026-07-05T12:00:00Z",
        "body_text": "Thanks for applying to the Backend Engineer role.",
    }


def test_classification_prompt_output_validates_structured_extraction() -> None:
    output = parse_classification_prompt_output(
        json.dumps(
            {
                "is_job_related": True,
                "category": "rejection",
                "confidence": 0.92,
                "company": "Example Systems",
                "role_title": "Backend Engineer",
                "application_status": "rejected",
                "event_type": "rejection",
                "event_at": "2026-07-05T12:00:00Z",
                "salary_min": 120000,
                "salary_max": 150000,
                "currency": "USD",
                "location": "Remote",
                "work_mode": "remote",
                "seniority": "senior",
                "sponsorship": "unknown",
                "tech_stack": ["Python", "FastAPI"],
                "rejection_reason": "The team selected candidates with more domain experience.",
            },
        ),
    )

    assert output.category is models.JobEmailCategory.REJECTION
    assert output.application_status == "rejected"
    assert output.event_type == "rejection"
    assert output.tech_stack == ("Python", "FastAPI")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "is_job_related": True,
            "category": "not_real",
            "confidence": 0.92,
            "company": "Example Systems",
            "role_title": "Backend Engineer",
            "application_status": "rejected",
            "event_type": "rejection",
            "event_at": "2026-07-05T12:00:00Z",
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "location": None,
            "work_mode": None,
            "seniority": None,
            "sponsorship": "unknown",
            "tech_stack": [],
            "rejection_reason": None,
        },
        {
            "is_job_related": True,
            "category": "rejection",
            "confidence": 0.92,
            "company": "Example Systems",
            "role_title": "Backend Engineer",
            "application_status": "rejected",
            "event_type": "rejection",
            "event_at": "2026-07-05T12:00:00Z",
            "salary_min": 150000,
            "salary_max": 120000,
            "currency": "USD",
            "location": None,
            "work_mode": None,
            "seniority": None,
            "sponsorship": "unknown",
            "tech_stack": [],
            "rejection_reason": None,
        },
        {
            "is_job_related": False,
            "category": "rejection",
            "confidence": 0.92,
            "company": None,
            "role_title": None,
            "application_status": None,
            "event_type": None,
            "event_at": None,
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "location": None,
            "work_mode": None,
            "seniority": None,
            "sponsorship": "unknown",
            "tech_stack": [],
            "rejection_reason": None,
        },
        {
            "is_job_related": True,
            "category": "rejection",
            "confidence": 0.92,
            "company": "Example Systems",
            "role_title": "Backend Engineer",
            "application_status": "rejected",
            "event_type": "rejection",
            "event_at": "2026-07-05T12:00:00Z",
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "location": None,
            "work_mode": None,
            "seniority": None,
            "sponsorship": "unknown",
            "tech_stack": [],
            "rejection_reason": None,
            "raw_sql": "select * from raw_emails",
        },
    ],
)
def test_classification_prompt_output_rejects_malformed_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        parse_classification_prompt_output(json.dumps(payload))
