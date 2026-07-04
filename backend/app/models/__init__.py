"""Pydantic DTOs used at application boundaries."""

from .health import HealthResponse
from .records import (
    ApplicationCorrectionRecord,
    ApplicationEventRecord,
    ApplicationRecord,
    ChatMessageRecord,
    InsightRecord,
    RawEmailRecord,
)
from .setup import SetupStatusResponse, SetupSubmitRequest, SetupSubmitResponse
from .synthetic_fixture import (
    SyntheticApplication,
    SyntheticApplicationEvent,
    SyntheticApplicationSource,
    SyntheticApplicationStatus,
    SyntheticBodyRetentionState,
    SyntheticEmailClassification,
    SyntheticEventType,
    SyntheticFixtureFile,
    SyntheticJobEmailCategory,
    SyntheticRawEmail,
    SyntheticSponsorship,
    SyntheticWorkMode,
)
from .wipe_data import WIPE_DATA_CONFIRMATION, WipeDataRequest, WipeDataResponse

__all__ = [
    "ApplicationCorrectionRecord",
    "ApplicationEventRecord",
    "ApplicationRecord",
    "ChatMessageRecord",
    "HealthResponse",
    "InsightRecord",
    "RawEmailRecord",
    "SetupStatusResponse",
    "SetupSubmitRequest",
    "SetupSubmitResponse",
    "SyntheticApplication",
    "SyntheticApplicationEvent",
    "SyntheticApplicationSource",
    "SyntheticApplicationStatus",
    "SyntheticBodyRetentionState",
    "SyntheticEmailClassification",
    "SyntheticEventType",
    "SyntheticFixtureFile",
    "SyntheticJobEmailCategory",
    "SyntheticRawEmail",
    "SyntheticSponsorship",
    "SyntheticWorkMode",
    "WIPE_DATA_CONFIRMATION",
    "WipeDataRequest",
    "WipeDataResponse",
]
