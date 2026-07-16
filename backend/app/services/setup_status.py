from __future__ import annotations

from app.config import AppSettings
from app.models import ReadinessState
from app.models.provider_config import ProviderReadinessResponse
from app.models.setup import SetupStatusResponse
from app.services.classification_mode_config import recommend_classification_mode


def build_setup_status(
    settings: AppSettings,
    readiness: ProviderReadinessResponse,
) -> SetupStatusResponse:
    return SetupStatusResponse(
        setup_complete=readiness.ready_to_sync and readiness.ready_to_classify,
        gmail_connected=readiness.gmail_sync.state
        in {ReadinessState.READY, ReadinessState.REAUTH_REQUIRED},
        llm_configured=readiness.classification_generation.state is ReadinessState.READY,
        email_provider=settings.email_provider,
        llm_provider=settings.llm_provider,
        classification_mode=settings.classification_mode,
        recommended_classification_mode=recommend_classification_mode(settings),
        readiness=readiness,
    )
