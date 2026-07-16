"""Repository interfaces and shared base classes."""

from .application import ApplicationRepository
from .attention import AttentionRepository
from .backfill_state import BackfillStateRepository
from .base import BaseRepository, SqlParameters
from .chat import ChatRepository
from .classification_run import ClassificationRunRepository
from .company_profile import CompanyProfileRepository
from .connection import EmailConnectionRepository
from .correction import CorrectionConflictRepository, CorrectionRepository
from .email import EmailRepository
from .email_chunk import EmailChunkRepository
from .event import EventRepository
from .filter_decision import EmailFilterDecisionRepository
from .insight import InsightRepository
from .metrics import MetricsRepository
from .pipeline_status import PipelineStatusRepository
from .provider_config import ProviderConfigurationRepository
from .sync_state import SyncStateRepository
from .synthetic_fixture import SyntheticFixtureRepository

__all__ = [
    "ApplicationRepository",
    "AttentionRepository",
    "BackfillStateRepository",
    "BaseRepository",
    "ChatRepository",
    "ClassificationRunRepository",
    "CompanyProfileRepository",
    "CorrectionConflictRepository",
    "CorrectionRepository",
    "EmailRepository",
    "EmailChunkRepository",
    "EmailConnectionRepository",
    "EmailFilterDecisionRepository",
    "EventRepository",
    "InsightRepository",
    "MetricsRepository",
    "PipelineStatusRepository",
    "ProviderConfigurationRepository",
    "SqlParameters",
    "SyncStateRepository",
    "SyntheticFixtureRepository",
]
