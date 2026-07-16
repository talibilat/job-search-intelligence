"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .aggregate import (
    ApplicationGroupingKey,
    build_application_grouping_key,
)
from .classify import (
    CLASSIFICATION_PROMPT_VERSION,
    ClassificationPromptEmail,
    JobApplicationExtraction,
    build_classification_prompt_request,
)

__all__ = [
    "ApplicationGroupingKey",
    "CLASSIFICATION_PROMPT_VERSION",
    "ClassificationPromptEmail",
    "JobApplicationExtraction",
    "build_classification_prompt_request",
    "build_application_grouping_key",
]
