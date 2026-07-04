from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.config import ClassificationMode, EmailProviderName, LLMProviderName
from app.providers import ProviderRequirementEnforcement
from app.security import SecretRef


class ProviderSelection(BaseModel):
    """Currently selected provider choices for the setup/config shell."""

    email_provider: EmailProviderName
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode


class ProviderConfigValues(BaseModel):
    """Non-secret provider settings visible at the API boundary."""

    gmail_client_config_file: Path
    gmail_scopes: tuple[str, ...]
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embedding_model: str


class ProviderConfigRequirementResponse(BaseModel):
    """Non-secret provider setting required by a supported provider."""

    setting_name: str
    label: str
    required: bool
    enforcement: ProviderRequirementEnforcement


class ProviderSecretRequirementResponse(BaseModel):
    """Secret reference metadata without the secret value."""

    ref: SecretRef
    label: str
    required: bool
    enforcement: ProviderRequirementEnforcement


class EmailProviderConfigResponse(BaseModel):
    """Email provider metadata exposed by the provider config API shell."""

    name: EmailProviderName
    display_name: str
    config_requirements: tuple[ProviderConfigRequirementResponse, ...]
    secret_requirements: tuple[ProviderSecretRequirementResponse, ...]


class LLMProviderConfigResponse(BaseModel):
    """LLM provider metadata exposed by the provider config API shell."""

    name: LLMProviderName
    display_name: str
    is_local: bool
    config_requirements: tuple[ProviderConfigRequirementResponse, ...]
    secret_requirements: tuple[ProviderSecretRequirementResponse, ...]


class ProviderConfigResponse(BaseModel):
    """Selected provider config plus supported provider metadata."""

    selection: ProviderSelection
    settings: ProviderConfigValues
    email_providers: tuple[EmailProviderConfigResponse, ...]
    llm_providers: tuple[LLMProviderConfigResponse, ...]


class ProviderConfigUpdateRequest(BaseModel):
    """Partial in-process update for non-secret Phase 0 provider config."""

    email_provider: EmailProviderName | None = None
    llm_provider: LLMProviderName | None = None
    classification_mode: ClassificationMode | None = None
    gmail_client_config_file: Path | None = None
    gmail_scopes: tuple[str, ...] | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = Field(default=None, min_length=1)
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    ollama_base_url: str | None = Field(default=None, min_length=1)
    ollama_chat_model: str | None = Field(default=None, min_length=1)
    ollama_embedding_model: str | None = Field(default=None, min_length=1)
