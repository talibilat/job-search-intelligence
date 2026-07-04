from __future__ import annotations

from app.config import AppSettings
from app.models import SetupStatusResponse


def build_setup_status(settings: AppSettings) -> SetupStatusResponse:
    return SetupStatusResponse(
        setup_complete=False,
        gmail_connected=False,
        llm_configured=False,
        email_provider=settings.email_provider,
        llm_provider=settings.llm_provider,
        classification_mode=settings.classification_mode,
    )
