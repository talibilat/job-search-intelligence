"""Repository interfaces and shared base classes."""

from .application import ApplicationRepository
from .backfill_state import BackfillStateRepository
from .base import BaseRepository, SqlParameters
from .chat import ChatRepository
from .classification_run import ClassificationRunRepository
from .connection import EmailConnectionRepository
from .correction import CorrectionConflictRepository, CorrectionRepository
from .email import EmailRepository
from .event import EventRepository
from .filter_decision import EmailFilterDecisionRepository
from .insight import InsightRepository
from .metrics import MetricsRepository
from .sync_state import SyncStateRepository
from .synthetic_fixture import SyntheticFixtureRepository

__all__ = [
    "ApplicationRepository",
    "BackfillStateRepository",
    "BaseRepository",
    "ChatRepository",
    "ClassificationRunRepository",
    "CorrectionConflictRepository",
    "CorrectionRepository",
    "EmailRepository",
    "EmailConnectionRepository",
    "EmailFilterDecisionRepository",
    "EventRepository",
    "InsightRepository",
    "MetricsRepository",
    "SqlParameters",
    "SyncStateRepository",
    "SyntheticFixtureRepository",
]
