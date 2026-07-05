from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models import JobEmailCategory
from app.pipeline.classify import (
    AcceptedLLMExtraction,
    MalformedLLMExtraction,
    MalformedLLMExtractionReason,
    parse_llm_extraction_response,
)
from app.providers.llm import LLMFinishReason, LLMGenerationResponse

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_parse_llm_extraction_response_rejects_invalid_json_without_classification() -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content="{not-json",
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.email_id == "email-1"
    assert result.model == "llama3.1"
    assert result.prompt_version == "classification-v1"
    assert result.reason is MalformedLLMExtractionReason.INVALID_JSON
    assert "not-json" not in repr(result)
    assert not hasattr(result, "classification")


def test_parse_llm_extraction_response_rejects_schema_errors_without_classification() -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=(
                '{"is_job_related":true,"category":"not_real",'
                '"confidence":1.4,"company":"Example Systems"}'
            ),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.INVALID_SCHEMA
    assert result.message == "LLM response failed structured extraction validation."
    assert not hasattr(result, "classification")


@pytest.mark.parametrize(
    "finish_reason",
    [
        LLMFinishReason.LENGTH,
        LLMFinishReason.TOOL_CALL,
        LLMFinishReason.CONTENT_FILTER,
        LLMFinishReason.ERROR,
        LLMFinishReason.UNKNOWN,
    ],
)
def test_parse_llm_extraction_response_rejects_unclean_finish_reasons(
    finish_reason: LLMFinishReason,
) -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=valid_structured_response_json(),
            model="llama3.1",
            finish_reason=finish_reason,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.INCOMPLETE_GENERATION
    assert result.message == "LLM response did not finish cleanly."
    assert not hasattr(result, "classification")


def test_parse_llm_extraction_response_rejects_blank_extracted_text() -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=(
                "{"
                '"is_job_related":true,'
                '"category":"application_confirmation",'
                '"confidence":0.88,'
                '"company":"   ",'
                '"role_title":"Backend Engineer"'
                "}"
            ),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.INVALID_SCHEMA
    assert not hasattr(result, "classification")


def test_parse_llm_extraction_response_rejects_stringly_typed_scalars() -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=(
                "{"
                '"is_job_related":"true",'
                '"category":"rejection",'
                '"confidence":"0.92",'
                '"salary_min":"120000",'
                '"company":"Example Systems",'
                '"role_title":"Backend Engineer"'
                "}"
            ),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.INVALID_SCHEMA
    assert not hasattr(result, "classification")


@pytest.mark.parametrize("event_at_json", ["1700000000", '"1700000000"'])
def test_parse_llm_extraction_response_rejects_numeric_event_at(
    event_at_json: str,
) -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=(
                "{"
                '"is_job_related":true,'
                '"category":"rejection",'
                '"confidence":0.92,'
                f'"event_at":{event_at_json},'
                '"company":"Example Systems",'
                '"role_title":"Backend Engineer"'
                "}"
            ),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.INVALID_SCHEMA
    assert not hasattr(result, "classification")


@pytest.mark.parametrize(
    "category",
    [
        "recruiter_outreach",
        "follow_up",
        "other",
    ],
)
def test_parse_llm_extraction_response_rejects_lifecycle_fields_for_non_lifecycle_categories(
    category: str,
) -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=(
                "{"
                '"is_job_related":true,'
                f'"category":"{category}",'
                '"confidence":0.92,'
                '"company":"Example Systems",'
                '"role_title":"Backend Engineer",'
                '"application_status":"rejected",'
                '"event_type":"rejection",'
                '"event_at":null,'
                '"salary_min":null,'
                '"salary_max":null,'
                '"currency":null,'
                '"location":null,'
                '"work_mode":null,'
                '"seniority":null,'
                '"sponsorship":"unknown",'
                '"tech_stack":[],'
                '"rejection_reason":null'
                "}"
            ),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.INVALID_SCHEMA
    assert not hasattr(result, "classification")


def test_parse_llm_extraction_response_rejects_duplicate_json_keys() -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=(
                "{"
                '"is_job_related":true,'
                '"category":"rejection",'
                '"confidence":1.4,'
                '"confidence":0.92,'
                '"company":"Example Systems",'
                '"role_title":"Backend Engineer"'
                "}"
            ),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, MalformedLLMExtraction)
    assert result.reason is MalformedLLMExtractionReason.DUPLICATE_JSON_KEY
    assert result.message == "LLM response contained duplicate JSON keys."
    assert not hasattr(result, "classification")


def test_parse_llm_extraction_response_accepts_valid_structured_extraction() -> None:
    result = parse_llm_extraction_response(
        email_id="email-1",
        response=LLMGenerationResponse(
            content=valid_structured_response_json(),
            model="llama3.1",
            finish_reason=LLMFinishReason.STOP,
        ),
        prompt_version="classification-v1",
        classified_at=NOW,
    )

    assert isinstance(result, AcceptedLLMExtraction)
    assert result.classification.email_id == "email-1"
    assert result.classification.category is JobEmailCategory.REJECTION
    assert result.classification.confidence == 0.92
    assert result.classification.model == "llama3.1"
    assert result.classification.prompt_version == "classification-v1"
    assert result.classification.classified_at == NOW
    assert result.extraction.company == "Example Systems"
    assert result.extraction.role_title == "Backend Engineer"
    assert result.extraction.status == "rejected"
    assert result.extraction.event_type == "rejection"
    assert result.extraction.tech_stack == ["Python", "FastAPI"]


def valid_structured_response_json() -> str:
    return (
        "{"
        '"is_job_related":true,'
        '"category":"rejection",'
        '"confidence":0.92,'
        '"company":"Example Systems",'
        '"role_title":"Backend Engineer",'
        '"application_status":"rejected",'
        '"event_type":"rejection",'
        '"event_at":"2026-07-04T12:30:00+00:00",'
        '"salary_min":120000,'
        '"salary_max":150000,'
        '"currency":"USD",'
        '"location":"Remote",'
        '"work_mode":"remote",'
        '"seniority":"senior",'
        '"sponsorship":"unknown",'
        '"tech_stack":["Python","FastAPI"],'
        '"rejection_reason":"The role was filled."'
        "}"
    )
