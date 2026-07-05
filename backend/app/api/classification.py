from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_readonly_email_repository
from app.config import AppSettings, get_settings
from app.db.repositories import EmailRepository
from app.models import ClassificationPreRunEstimate
from app.services.classification_estimate import build_classification_pre_run_estimate

router = APIRouter(prefix="/classification", tags=["classification"])


@router.get(
    "/estimate",
    response_model=ClassificationPreRunEstimate,
    summary="Estimate Classification Run",
    description=(
        "Returns deterministic candidate counts, token estimates, and cost availability "
        "for a future bulk classification pass without calling an LLM or exposing email content."
    ),
)
async def classification_estimate(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[
        EmailRepository,
        Depends(get_readonly_email_repository),
    ],
) -> ClassificationPreRunEstimate:
    return build_classification_pre_run_estimate(
        settings=settings,
        email_repository=email_repository,
    )
