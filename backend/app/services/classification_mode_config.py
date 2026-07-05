from __future__ import annotations

from app.config import AppSettings, ClassificationMode, LLMProviderName


def recommend_classification_mode(settings: AppSettings) -> ClassificationMode:
    """Return the setup preselection for the selected LLM provider."""

    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return ClassificationMode.HYBRID

    return ClassificationMode.LOCAL
