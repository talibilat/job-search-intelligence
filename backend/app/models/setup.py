from __future__ import annotations

from pydantic import BaseModel

from app.config import ClassificationMode, EmailProviderName, LLMProviderName


class SetupStatusResponse(BaseModel):
    """First-run setup readiness and selected non-secret provider settings."""

    setup_complete: bool
    gmail_connected: bool
    llm_configured: bool
    email_provider: EmailProviderName
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode
