from __future__ import annotations

from typing import Protocol

from app.config import AppSettings, EmailProviderName
from app.models import SetupStatusResponse
from app.providers.email import EmailConnection


class EmailConnectionStatusReader(Protocol):
    def fetch_default_connection_metadata(
        self,
        provider: EmailProviderName,
    ) -> EmailConnection | None: ...


def build_setup_status(
    settings: AppSettings,
    connection_reader: EmailConnectionStatusReader | None = None,
) -> SetupStatusResponse:
    gmail_connected = False
    if connection_reader is not None:
        gmail_connected = (
            connection_reader.fetch_default_connection_metadata(settings.email_provider) is not None
        )

    return SetupStatusResponse(
        setup_complete=False,
        gmail_connected=gmail_connected,
        llm_configured=False,
        email_provider=settings.email_provider,
        llm_provider=settings.llm_provider,
        classification_mode=settings.classification_mode,
    )
