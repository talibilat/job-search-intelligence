from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from app.models.application import ApplicationStatus, SponsorshipStatus, WorkMode
from app.models.classification import (
    ClassificationPromptOutput,
    EmailClassificationRecord,
    JobEmailCategory,
)
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMResponseFormat,
)

type NonBlankString = Annotated[StrictStr, Field(min_length=1)]

CLASSIFICATION_PROMPT_VERSION = "v1"
CLASSIFICATION_MAX_OUTPUT_TOKENS = 1200


class ClassificationPromptEmail(BaseModel):
    """Retained email content passed into the classification prompt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email_id: str = Field(min_length=1)
    from_addr: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, min_length=1)
    sent_at: datetime | None = None
    body_text: str = Field(min_length=1, repr=False)

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "email_id": self.email_id,
            "from_addr": self.from_addr,
            "subject": self.subject,
            "sent_at": _format_prompt_datetime(self.sent_at),
            "body_text": self.body_text,
        }


class MalformedLLMExtractionReason(StrEnum):
    INVALID_JSON = "invalid_json"
    INVALID_SCHEMA = "invalid_schema"
    INCOMPLETE_GENERATION = "incomplete_generation"
    DUPLICATE_JSON_KEY = "duplicate_json_key"


class _DuplicateJSONKeyError(ValueError):
    """Raised when provider JSON repeats a key in the same object."""


class JobApplicationExtraction(BaseModel):
    """Structured application fields extracted from one job-search email."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: NonBlankString | None = None
    role_title: NonBlankString | None = None
    status: ApplicationStatus | None = None
    event_at: datetime | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: NonBlankString | None = None
    location: NonBlankString | None = None
    work_mode: WorkMode | None = None
    seniority: NonBlankString | None = None
    sponsorship: SponsorshipStatus = "unknown"
    tech_stack: list[NonBlankString] = Field(default_factory=list)
    rejection_reason: NonBlankString | None = None

    @field_validator(
        "company",
        "role_title",
        "currency",
        "location",
        "seniority",
        "rejection_reason",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("tech_stack", mode="before")
    @classmethod
    def strip_tech_stack_items(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return [item.strip() if isinstance(item, str) else item for item in value]
        return value

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def require_integer_salary(cls, value: object) -> object:
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, int):
            msg = "salary values must be JSON integers"
            raise ValueError(msg)
        return value

    @field_validator("event_at", mode="before")
    @classmethod
    def reject_numeric_event_at(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, int | float):
            msg = "event_at must be an ISO datetime string"
            raise ValueError(msg)
        if isinstance(value, str):
            stripped_value = value.strip()
            if _is_numeric_string(stripped_value):
                msg = "event_at must be an ISO datetime string"
                raise ValueError(msg)
            return stripped_value
        return value

    @model_validator(mode="after")
    def validate_salary_range(self) -> Self:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            msg = "salary_min must be less than or equal to salary_max"
            raise ValueError(msg)
        return self


class AcceptedLLMExtraction(BaseModel):
    """Validated classification and extraction safe for downstream storage."""

    model_config = ConfigDict(frozen=True)

    classification: EmailClassificationRecord
    extraction: JobApplicationExtraction


class MalformedLLMExtraction(BaseModel):
    """Public-safe quarantine result for malformed provider output."""

    model_config = ConfigDict(frozen=True)

    email_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    reason: MalformedLLMExtractionReason
    message: str = Field(min_length=1)


type LLMExtractionResult = AcceptedLLMExtraction | MalformedLLMExtraction


class _LLMExtractionPayload(JobApplicationExtraction):
    is_job_related: bool
    category: JobEmailCategory
    confidence: float = Field(ge=0, le=1)

    @field_validator("is_job_related", mode="before")
    @classmethod
    def require_boolean_classification(cls, value: object) -> object:
        if not isinstance(value, bool):
            msg = "is_job_related must be a JSON boolean"
            raise ValueError(msg)
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def require_numeric_confidence(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = "confidence must be a JSON number"
            raise ValueError(msg)
        return float(value)


def build_classification_prompt_request(
    email: ClassificationPromptEmail,
    *,
    prompt_version: str = CLASSIFICATION_PROMPT_VERSION,
    model: str | None = None,
) -> LLMGenerationRequest:
    """Build the provider-neutral JSON request for classifying one email."""

    if not prompt_version:
        msg = "prompt_version must not be empty"
        raise ValueError(msg)

    return LLMGenerationRequest(
        messages=(
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content=_classification_system_prompt(prompt_version=prompt_version),
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content=json.dumps(email.to_prompt_payload(), sort_keys=False),
            ),
        ),
        model=model,
        response_format=LLMResponseFormat.JSON_OBJECT,
        options=LLMGenerationOptions(
            temperature=0,
            max_output_tokens=CLASSIFICATION_MAX_OUTPUT_TOKENS,
        ),
    )


def parse_classification_prompt_output(content: str) -> ClassificationPromptOutput:
    """Validate and parse JSON returned by the classification prompt."""

    return ClassificationPromptOutput.model_validate_json(content)


def parse_llm_extraction_response(
    *,
    email_id: str,
    response: LLMGenerationResponse,
    prompt_version: str,
    classified_at: datetime,
) -> LLMExtractionResult:
    """Validate one LLM extraction response before any storage side effects."""

    if response.finish_reason != LLMFinishReason.STOP:
        return _malformed_result(
            email_id=email_id,
            response=response,
            prompt_version=prompt_version,
            reason=MalformedLLMExtractionReason.INCOMPLETE_GENERATION,
            message="LLM response did not finish cleanly.",
        )

    try:
        raw_payload = json.loads(
            response.content,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except _DuplicateJSONKeyError:
        return _malformed_result(
            email_id=email_id,
            response=response,
            prompt_version=prompt_version,
            reason=MalformedLLMExtractionReason.DUPLICATE_JSON_KEY,
            message="LLM response contained duplicate JSON keys.",
        )
    except json.JSONDecodeError:
        return _malformed_result(
            email_id=email_id,
            response=response,
            prompt_version=prompt_version,
            reason=MalformedLLMExtractionReason.INVALID_JSON,
            message="LLM response was not valid JSON.",
        )

    if not isinstance(raw_payload, dict):
        return _malformed_result(
            email_id=email_id,
            response=response,
            prompt_version=prompt_version,
            reason=MalformedLLMExtractionReason.INVALID_SCHEMA,
            message="LLM response failed structured extraction validation.",
        )

    try:
        payload = _LLMExtractionPayload.model_validate(raw_payload)
        classification = EmailClassificationRecord(
            email_id=email_id,
            is_job_related=payload.is_job_related,
            category=payload.category,
            confidence=payload.confidence,
            model=response.model,
            prompt_version=prompt_version,
            classified_at=classified_at,
        )
    except ValidationError:
        return _malformed_result(
            email_id=email_id,
            response=response,
            prompt_version=prompt_version,
            reason=MalformedLLMExtractionReason.INVALID_SCHEMA,
            message="LLM response failed structured extraction validation.",
        )

    extraction = JobApplicationExtraction.model_validate(
        payload.model_dump(
            exclude={"is_job_related", "category", "confidence"},
        ),
    )
    return AcceptedLLMExtraction(classification=classification, extraction=extraction)


def _classification_system_prompt(*, prompt_version: str) -> str:
    schema = json.dumps(
        ClassificationPromptOutput.model_json_schema(),
        sort_keys=True,
    )
    categories = ", ".join(category.value for category in JobEmailCategory)

    return "\n".join(
        (
            "You classify retained job-search email candidates for JobTracker.",
            f"Prompt version: {prompt_version}",
            "Return exactly one JSON object. Do not wrap it in Markdown.",
            f"Allowed categories: {categories}.",
            "Use null for unknown nullable fields, sponsorship unknown when unclear, "
            "and tech_stack as an array.",
            "For non-job-related messages, set is_job_related false, category other, "
            "nullable extraction fields to null, sponsorship unknown, and tech_stack [].",
            "Do not include extra fields, raw SQL, counts, secrets, or provider payloads.",
            "The JSON object must match this schema:",
            schema,
        ),
    )


def _format_prompt_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    formatted = value.isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()

    return formatted.replace("+00:00", "Z")


def _malformed_result(
    *,
    email_id: str,
    response: LLMGenerationResponse,
    prompt_version: str,
    reason: MalformedLLMExtractionReason,
    message: str,
) -> MalformedLLMExtraction:
    return MalformedLLMExtraction(
        email_id=email_id,
        model=response.model,
        prompt_version=prompt_version,
        reason=reason,
        message=message,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise _DuplicateJSONKeyError
        payload[key] = value
    return payload


def _is_numeric_string(value: str) -> bool:
    if not value:
        return False
    try:
        float(value)
    except ValueError:
        return False
    return True
