from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.classification import ClassificationPromptOutput, JobEmailCategory
from app.providers.llm import (
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMResponseFormat,
)

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
