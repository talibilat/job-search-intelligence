"""Pydantic DTOs used at application boundaries."""

from .metrics import MetricsFilter
from .processing import (
    ProcessingRunRequest,
    ProcessingRunResult,
    ProcessingRunState,
    ProcessingStatus,
)
from .records import (
    ApplicationCorrectionRecord,
    ApplicationEventRecord,
    ApplicationRecord,
    ChatMessageRecord,
    ClassificationRunRecord,
    EmailCandidateQueryStrategy,
    EmailChunkRecord,
    EmailClassificationCandidate,
    EmailClassificationRecord,
    EmailClassificationResult,
    EmailConnectionRecord,
    EmailFilterDecisionOutcome,
    EmailFilterDecisionRecord,
    InsightRecord,
    JobEmailCategory,
    RawEmailBodyRetentionState,
    RawEmailRecord,
)

__all__ = [
    "MetricsFilter",
    "ProcessingRunRequest",
    "ProcessingRunResult",
    "ProcessingRunState",
    "ProcessingStatus",
    "ApplicationCorrectionRecord",
    "ApplicationEventRecord",
    "ApplicationRecord",
    "ChatMessageRecord",
    "ClassificationRunRecord",
    "EmailCandidateQueryStrategy",
    "EmailChunkRecord",
    "EmailClassificationCandidate",
    "EmailClassificationRecord",
    "EmailClassificationResult",
    "EmailConnectionRecord",
    "EmailFilterDecisionOutcome",
    "EmailFilterDecisionRecord",
    "InsightRecord",
    "JobEmailCategory",
    "RawEmailBodyRetentionState",
    "RawEmailRecord",
]
