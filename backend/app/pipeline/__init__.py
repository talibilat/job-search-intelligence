"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .classify import (
    CLASSIFICATION_PROMPT_VERSION,
    ClassificationPromptEmail,
    build_classification_prompt_request,
    parse_classification_prompt_output,
)

__all__ = [
    "CLASSIFICATION_PROMPT_VERSION",
    "ClassificationPromptEmail",
    "build_classification_prompt_request",
    "parse_classification_prompt_output",
]
