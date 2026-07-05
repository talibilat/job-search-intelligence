from __future__ import annotations

from app.config import AppSettings, LLMProviderName


def resolve_classification_model(settings: AppSettings) -> str:
    """Return the configured chat model used for classification version checks."""

    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return settings.azure_openai_chat_deployment or "unconfigured"
    return settings.ollama_chat_model
