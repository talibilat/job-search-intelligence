from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.config import (
    ClassificationMode,
    EmailProviderName,
    LLMProviderName,
    WebSearchProviderName,
)
from app.providers import ProviderRequirementEnforcement
from app.security import SecretRef


class ProviderSelection(BaseModel):
    """Currently selected provider choices for the setup/config shell."""

    email_provider: EmailProviderName
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode


class ProviderConfigValues(BaseModel):
    """Non-secret provider settings visible at the API boundary."""

    gmail_scopes: tuple[str, ...]
    sync_on_open: bool
    sync_interval_seconds: int
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embedding_model: str
    web_search_provider: WebSearchProviderName
    web_search_enabled: bool
    tavily_base_url: str
    web_search_max_results: int = Field(ge=1, le=10)
    web_search_timeout_seconds: int = Field(ge=1, le=120)


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
    recommended_classification_mode: ClassificationMode
    settings: ProviderConfigValues
    email_providers: tuple[EmailProviderConfigResponse, ...]
    llm_providers: tuple[LLMProviderConfigResponse, ...]


class ProviderConfigUpdateRequest(BaseModel):
    """Partial durable provider config update with write-only credentials."""

    model_config = ConfigDict(extra="forbid")

    email_provider: EmailProviderName | None = None
    llm_provider: LLMProviderName | None = None
    classification_mode: ClassificationMode | None = None
    gmail_oauth_client_json: SecretStr | None = None
    azure_openai_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    sync_on_open: bool | None = None
    sync_interval_seconds: int | None = Field(default=None, ge=60, le=86_400)
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = Field(default=None, min_length=1)
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    ollama_base_url: str | None = Field(default=None, min_length=1)
    ollama_chat_model: str | None = Field(default=None, min_length=1)
    ollama_embedding_model: str | None = Field(default=None, min_length=1)
    web_search_enabled: bool | None = None
    web_search_provider: WebSearchProviderName | None = None
    tavily_base_url: str | None = Field(default=None, min_length=1)
    web_search_max_results: int | None = Field(default=None, ge=1, le=10)
    web_search_timeout_seconds: int | None = Field(default=None, ge=1, le=120)


class LLMProviderHealthCheckApiRequest(BaseModel):
    """Empty request body accepted by the LLM provider health endpoint."""

    model_config = ConfigDict(extra="forbid")


class ProviderConfigurationRecord(BaseModel):
    """Typed singleton row containing only non-secret operational settings."""

    email_provider: EmailProviderName
    llm_provider: LLMProviderName
    classification_mode: ClassificationMode
    sync_on_open: bool
    sync_interval_seconds: int = Field(ge=60, le=86_400)
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embedding_model: str
    web_search_enabled: bool
    web_search_provider: WebSearchProviderName
    tavily_base_url: str
    web_search_max_results: int = Field(ge=1, le=10)
    web_search_timeout_seconds: int = Field(ge=1, le=120)
    updated_at: datetime


class ReadinessState(StrEnum):
    READY = "ready"
    MISSING_CONFIG = "missing_config"
    MISSING_CREDENTIAL = "missing_credential"
    UNAVAILABLE = "unavailable"
    REAUTH_REQUIRED = "reauth_required"
    NOT_IMPLEMENTED = "not_implemented"
    DISABLED = "disabled"


class CapabilityReadiness(BaseModel):
    state: ReadinessState
    message: str
    action: str | None = None


class ProviderReadinessResponse(BaseModel):
    ready_to_sync: bool
    ready_to_classify: bool
    gmail_sync: CapabilityReadiness
    classification_generation: CapabilityReadiness
    embedding_generation: CapabilityReadiness
    chat_generation: CapabilityReadiness
    web_search: CapabilityReadiness
