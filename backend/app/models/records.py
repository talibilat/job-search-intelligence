from __future__ import annotations

from app.models.application import (
    ApplicationRecord,
    ApplicationSource,
    ApplicationStatus,
    SponsorshipStatus,
    WorkMode,
)
from app.models.chat import ChatMessageRecord, ChatMessageRole
from app.models.chunk import EmailChunkRecord
from app.models.classification import (
    ClassificationRunRecord,
    EmailClassificationRecord,
    JobEmailCategory,
)
from app.models.connection import EmailConnectionRecord
from app.models.correction import (
    ApplicationCorrectionRecord,
    CorrectionType,
    JsonObject,
    JsonObjectList,
)
from app.models.event import ApplicationEventRecord, ApplicationEventType
from app.models.filter_decision import EmailFilterDecisionOutcome, EmailFilterDecisionRecord
from app.models.insight import InsightRecord, InsightType
from app.models.raw_email import RawEmailBodyRetentionState, RawEmailRecord
from app.models.sync_state import (
    EmailBackfillStateRecord,
    EmailBackfillStatus,
    EmailSyncStateRecord,
)

__all__ = [
    "ApplicationCorrectionRecord",
    "ApplicationEventRecord",
    "ApplicationEventType",
    "ApplicationRecord",
    "ApplicationSource",
    "ApplicationStatus",
    "ChatMessageRecord",
    "ChatMessageRole",
    "ClassificationRunRecord",
    "CorrectionType",
    "EmailBackfillStateRecord",
    "EmailBackfillStatus",
    "EmailChunkRecord",
    "EmailClassificationRecord",
    "EmailConnectionRecord",
    "EmailFilterDecisionOutcome",
    "EmailFilterDecisionRecord",
    "EmailSyncStateRecord",
    "InsightRecord",
    "InsightType",
    "JobEmailCategory",
    "JsonObject",
    "JsonObjectList",
    "RawEmailBodyRetentionState",
    "RawEmailRecord",
    "SponsorshipStatus",
    "WorkMode",
]
