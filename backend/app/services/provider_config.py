from __future__ import annotations

from typing import Any

from app.config import AppSettings
from app.models import (
    EmailProviderConfigResponse,
    LLMProviderConfigResponse,
    ProviderConfigRequirementResponse,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
    ProviderConfigValues,
    ProviderSecretRequirementResponse,
    ProviderSelection,
)
from app.providers import (
    EmailProviderRegistration,
    LLMProviderRegistration,
    ProviderConfigRequirement,
    ProviderRegistry,
    ProviderSecretRequirement,
)
from app.services.classification_mode_config import recommend_classification_mode


def build_provider_config_response(
    settings: AppSettings,
    registry: ProviderRegistry,
) -> ProviderConfigResponse:
    """Build the non-secret provider config API response."""

    return ProviderConfigResponse(
        selection=ProviderSelection(
            email_provider=settings.email_provider,
            llm_provider=settings.llm_provider,
            classification_mode=settings.classification_mode,
        ),
        recommended_classification_mode=recommend_classification_mode(settings),
        settings=ProviderConfigValues(
            gmail_client_config_file=settings.gmail_client_config_file,
            gmail_scopes=settings.gmail_scopes,
            azure_openai_endpoint=settings.azure_openai_endpoint,
            azure_openai_api_version=settings.azure_openai_api_version,
            azure_openai_chat_deployment=settings.azure_openai_chat_deployment,
            azure_openai_embedding_deployment=settings.azure_openai_embedding_deployment,
            ollama_base_url=settings.ollama_base_url,
            ollama_chat_model=settings.ollama_chat_model,
            ollama_embedding_model=settings.ollama_embedding_model,
        ),
        email_providers=tuple(
            _email_provider_response(provider) for provider in registry.email_providers()
        ),
        llm_providers=tuple(
            _llm_provider_response(provider) for provider in registry.llm_providers()
        ),
    )


def apply_provider_config_update(
    settings: AppSettings,
    request: ProviderConfigUpdateRequest,
    registry: ProviderRegistry,
) -> ProviderConfigResponse:
    """Validate and apply a Phase 0 in-process provider config update."""

    updates = request.model_dump(exclude_none=True, exclude_unset=True)
    updated_settings = _updated_settings(settings, updates)
    registry.validate_settings(updated_settings)

    fields_to_apply = set(updates)
    if "llm_provider" in updates and "classification_mode" not in updates:
        fields_to_apply.add("classification_mode")

    for field_name in fields_to_apply:
        setattr(settings, field_name, getattr(updated_settings, field_name))

    return build_provider_config_response(settings, registry)


def _updated_settings(settings: AppSettings, updates: dict[str, Any]) -> AppSettings:
    values = settings.model_dump()
    values.update(updates)
    if "llm_provider" in updates and "classification_mode" not in updates:
        candidate_settings = AppSettings(_env_file=None, **values)
        values["classification_mode"] = recommend_classification_mode(candidate_settings)
    return AppSettings(_env_file=None, **values)


def _config_requirement_response(
    requirement: ProviderConfigRequirement,
) -> ProviderConfigRequirementResponse:
    return ProviderConfigRequirementResponse(
        setting_name=requirement.setting_name,
        label=requirement.label,
        required=requirement.required,
        enforcement=requirement.enforcement,
    )


def _secret_requirement_response(
    requirement: ProviderSecretRequirement,
) -> ProviderSecretRequirementResponse:
    return ProviderSecretRequirementResponse(
        ref=requirement.ref,
        label=requirement.label,
        required=requirement.required,
        enforcement=requirement.enforcement,
    )


def _email_provider_response(
    provider: EmailProviderRegistration,
) -> EmailProviderConfigResponse:
    return EmailProviderConfigResponse(
        name=provider.name,
        display_name=provider.display_name,
        config_requirements=tuple(
            _config_requirement_response(requirement)
            for requirement in provider.config_requirements
        ),
        secret_requirements=tuple(
            _secret_requirement_response(requirement)
            for requirement in provider.secret_requirements
        ),
    )


def _llm_provider_response(provider: LLMProviderRegistration) -> LLMProviderConfigResponse:
    return LLMProviderConfigResponse(
        name=provider.name,
        display_name=provider.display_name,
        is_local=provider.is_local,
        config_requirements=tuple(
            _config_requirement_response(requirement)
            for requirement in provider.config_requirements
        ),
        secret_requirements=tuple(
            _secret_requirement_response(requirement)
            for requirement in provider.secret_requirements
        ),
    )
