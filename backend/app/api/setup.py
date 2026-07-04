from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import AppSettings, get_settings
from app.models import SetupStatusResponse
from app.services.setup_status import build_setup_status

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SetupStatusResponse:
    """Report the Phase 0 setup shell without validating or exposing secrets."""

    return build_setup_status(settings)
