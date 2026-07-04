from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import ClassificationMode, EmailProviderName, LLMProviderName


class SetupStatusResponse(BaseModel):
    """First-run setup readiness and selected non-secret provider settings."""

    setup_complete: bool
    gmail_connected: bool
    llm_configured: bool
    email_provider: EmailProviderName
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode


class SetupSubmitRequest(BaseModel):
    """Non-secret first-run setup choices accepted by the Phase 0 API shell."""

    model_config = ConfigDict(extra="forbid")

    email_provider: EmailProviderName = EmailProviderName.GMAIL
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode
    gmail_client_config_file: Path | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    ollama_base_url: str | None = None
    ollama_chat_model: str | None = None
    ollama_embedding_model: str | None = None


class SetupSubmitResponse(SetupStatusResponse):
    """Acknowledgement for a setup submission that has not persisted secrets yet."""

    status: Literal["accepted"]
