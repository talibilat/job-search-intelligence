from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SyncLocalStats(BaseModel):
    """Deterministic totals over locally stored raw-email metadata."""

    model_config = ConfigDict(frozen=True)

    total_raw_emails: int = Field(ge=0)
    last_run_at: datetime | None = None


class SyncScopeEstimateBasis(StrEnum):
    """How a pre-sync scope estimate was derived."""

    FULL_BACKFILL = "full_backfill"
    MESSAGE_CAP = "message_cap"
    UNKNOWN_INCREMENTAL = "unknown_incremental"
    UNKNOWN_INCREMENTAL_WINDOW = "unknown_incremental_window"


class SyncScopeEstimate(BaseModel):
    """Deterministic local approximation of how much email a sync scope covers.

    Derived only from already-synced local metadata; it never calls the provider.
    """

    model_config = ConfigDict(frozen=True)

    estimated_message_count: int | None = Field(default=None, ge=0)
    basis: SyncScopeEstimateBasis
    window_start: datetime | None = None
    window_end: datetime | None = None
    total_local_emails: int = Field(ge=0)
