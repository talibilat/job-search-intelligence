"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .classify import (
    CLASSIFICATION_PROMPT_VERSION,
    AcceptedLLMExtraction,
    ClassificationPromptEmail,
    JobApplicationExtraction,
    LLMExtractionResult,
    MalformedLLMExtraction,
    MalformedLLMExtractionReason,
    build_classification_prompt_request,
    parse_classification_prompt_output,
    parse_llm_extraction_response,
)

__all__ = [
    "CLASSIFICATION_PROMPT_VERSION",
    "AcceptedLLMExtraction",
    "ClassificationPromptEmail",
    "JobApplicationExtraction",
    "LLMExtractionResult",
    "MalformedLLMExtraction",
    "MalformedLLMExtractionReason",
    "build_classification_prompt_request",
    "parse_classification_prompt_output",
    "parse_llm_extraction_response",
]
