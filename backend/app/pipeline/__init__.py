"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .classify import (
    CLASSIFICATION_PROMPT_VERSION,
    ClassificationPromptEmail,
    JobApplicationExtraction,
    build_classification_prompt_request,
)

__all__ = [
    "CLASSIFICATION_PROMPT_VERSION",
    "ClassificationPromptEmail",
    "JobApplicationExtraction",
    "build_classification_prompt_request",
]
