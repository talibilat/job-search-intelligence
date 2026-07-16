"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .aggregate import (
    ApplicationGroupingKey,
    build_application_grouping_key,
)
from .classify import (
    CLASSIFICATION_PROMPT_VERSION,
    AcceptedLLMExtraction,
    ClassificationPromptEmail,
    JobApplicationExtraction,
    MalformedLLMExtraction,
    MalformedLLMExtractionReason,
    build_classification_prompt_request,
    parse_classification_prompt_output,
    parse_llm_extraction_response,
)

__all__ = [
    "ApplicationGroupingKey",
    "CLASSIFICATION_PROMPT_VERSION",
    "AcceptedLLMExtraction",
    "ClassificationPromptEmail",
    "JobApplicationExtraction",
    "MalformedLLMExtraction",
    "MalformedLLMExtractionReason",
    "build_classification_prompt_request",
    "build_application_grouping_key",
    "parse_classification_prompt_output",
    "parse_llm_extraction_response",
]
