from __future__ import annotations

from fastapi import APIRouter

from app.models import SyncJobStatus
from app.services.sync_service import build_idle_sync_status

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status", response_model=SyncJobStatus)
async def sync_status() -> SyncJobStatus:
    """Report the current email sync job status without exposing provider payloads."""

    return build_idle_sync_status()
