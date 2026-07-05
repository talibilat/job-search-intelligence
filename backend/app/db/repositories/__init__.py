"""Repository interfaces and shared base classes."""

from .application import ApplicationRepository
from .backfill_state import BackfillStateRepository
from .base import BaseRepository, SqlParameters
from .chat import ChatRepository
from .connection import EmailConnectionRepository
from .correction import CorrectionRepository
from .email import EmailRepository
from .event import EventRepository
from .insight import InsightRepository
from .sync_state import SyncStateRepository
from .synthetic_fixture import SyntheticFixtureRepository

__all__ = [
    "ApplicationRepository",
    "BackfillStateRepository",
    "BaseRepository",
    "ChatRepository",
    "CorrectionRepository",
    "EmailRepository",
    "EmailConnectionRepository",
    "EventRepository",
    "InsightRepository",
    "SqlParameters",
    "SyncStateRepository",
    "SyntheticFixtureRepository",
]
