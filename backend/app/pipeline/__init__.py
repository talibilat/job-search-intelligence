"""Pipeline stages for ingest, filter, classify, and aggregate."""

from .classify import (
    ClassificationPromptEmail,
    JobApplicationExtraction,
)

__all__ = [
    "ClassificationPromptEmail",
    "JobApplicationExtraction",
]
