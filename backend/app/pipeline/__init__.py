"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .classify import (
    ClassificationPromptEmail,
    JobApplicationExtraction,
    build_classification_prompt_request,
)

__all__ = [
    "ClassificationPromptEmail",
    "JobApplicationExtraction",
    "build_classification_prompt_request",
]
