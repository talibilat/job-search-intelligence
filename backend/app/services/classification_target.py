from __future__ import annotations

from app.config import AppSettings, LLMProviderName


def resolve_classification_model(settings: AppSettings) -> str:
    """Return the configured chat model used for classification version checks."""

    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return settings.azure_openai_chat_deployment
    return settings.ollama_chat_model


def has_configured_classification_model(settings: AppSettings) -> bool:
    """Return whether the selected LLM provider has a runnable classification model."""

    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return bool(settings.azure_openai_chat_deployment)
    return bool(settings.ollama_chat_model)
