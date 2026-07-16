from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.config import AppSettings, normalize_azure_openai_endpoint
from app.db.repositories.provider_config import ProviderConfigurationRepository
from app.models.provider_config import (
    EmailProviderConfigResponse,
    LLMProviderConfigResponse,
    ProviderConfigRequirementResponse,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
    ProviderConfigurationRecord,
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
from app.providers.email.gmail import GoogleOAuthClientConfig
from app.security import (
    AZURE_OPENAI_API_KEY_REF,
    GMAIL_OAUTH_CLIENT_REF,
    SecretStore,
)
from app.services.classification_mode_config import recommend_classification_mode
from app.services.sync_service import SyncScheduler

_PERSISTED_FIELDS = (
    "email_provider",
    "llm_provider",
    "classification_mode",
    "sync_on_open",
    "sync_interval_seconds",
    "azure_openai_endpoint",
    "azure_openai_api_version",
    "azure_openai_chat_deployment",
    "azure_openai_embedding_deployment",
    "ollama_base_url",
    "ollama_chat_model",
    "ollama_embedding_model",
)
_SECRET_FIELDS = {"azure_openai_api_key", "gmail_oauth_client_json"}


class SyncSchedulerConfigurationError(RuntimeError):
    """Raised when validated sync settings cannot be applied to the scheduler."""


def apply_persisted_provider_config(
    settings: AppSettings,
    record: ProviderConfigurationRecord | None,
) -> None:
    """Overlay UI-persisted operational fields on environment bootstrap defaults."""

    if record is None:
        return
    for field_name in _PERSISTED_FIELDS:
        setattr(settings, field_name, getattr(record, field_name))
    settings.azure_openai_endpoint = normalize_azure_openai_endpoint(settings.azure_openai_endpoint)


def build_provider_config_response(
    settings: AppSettings,
    registry: ProviderRegistry,
) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        selection=ProviderSelection(
            email_provider=settings.email_provider,
            llm_provider=settings.llm_provider,
            classification_mode=settings.classification_mode,
        ),
        recommended_classification_mode=recommend_classification_mode(settings),
        settings=ProviderConfigValues(
            gmail_scopes=settings.gmail_scopes,
            sync_on_open=settings.sync_on_open,
            sync_interval_seconds=settings.sync_interval_seconds,
            azure_openai_endpoint=settings.azure_openai_endpoint,
            azure_openai_api_version=settings.azure_openai_api_version,
            azure_openai_chat_deployment=settings.azure_openai_chat_deployment,
            azure_openai_embedding_deployment=settings.azure_openai_embedding_deployment,
            ollama_base_url=settings.ollama_base_url,
            ollama_chat_model=settings.ollama_chat_model,
            ollama_embedding_model=settings.ollama_embedding_model,
        ),
        email_providers=tuple(
            _email_provider_response(item) for item in registry.email_providers()
        ),
        llm_providers=tuple(_llm_provider_response(item) for item in registry.llm_providers()),
    )


async def apply_provider_config_update(
    settings: AppSettings,
    request: ProviderConfigUpdateRequest,
    registry: ProviderRegistry,
    *,
    repository: ProviderConfigurationRepository,
    secret_store: SecretStore,
    sync_scheduler: SyncScheduler,
) -> ProviderConfigResponse:
    """Validate, securely store credentials, and durably apply provider settings."""

    request_values = request.model_dump(exclude_none=True, exclude_unset=True)
    updates = {key: value for key, value in request_values.items() if key not in _SECRET_FIELDS}
    if "azure_openai_endpoint" in updates:
        updates["azure_openai_endpoint"] = normalize_azure_openai_endpoint(
            str(updates["azure_openai_endpoint"])
        )
    updated_settings = _updated_settings(settings, updates)
    registry.validate_settings(updated_settings)
    await _store_credentials(request, secret_store)

    if {"sync_on_open", "sync_interval_seconds"} & updates.keys():
        try:
            sync_scheduler.reconfigure(
                sync_on_open=updated_settings.sync_on_open,
                interval_seconds=updated_settings.sync_interval_seconds,
            )
        except Exception as error:
            raise SyncSchedulerConfigurationError from error

    repository.save(updated_settings)
    for field_name in _PERSISTED_FIELDS:
        setattr(settings, field_name, getattr(updated_settings, field_name))
    return build_provider_config_response(settings, registry)


async def _store_credentials(
    request: ProviderConfigUpdateRequest,
    secret_store: SecretStore,
) -> None:
    if request.gmail_oauth_client_json is not None:
        raw_json = request.gmail_oauth_client_json.get_secret_value()
        try:
            parsed = json.loads(raw_json)
            GoogleOAuthClientConfig.model_validate(parsed)
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("Google OAuth client JSON is invalid.") from error
        await secret_store.set_secret(GMAIL_OAUTH_CLIENT_REF, SecretStr(raw_json))
    if request.azure_openai_api_key is not None:
        api_key = request.azure_openai_api_key.get_secret_value().strip()
        if not api_key:
            raise ValueError("Azure OpenAI API key cannot be blank.")
        await secret_store.set_secret(AZURE_OPENAI_API_KEY_REF, SecretStr(api_key))


async def import_azure_openai_api_key_from_environment(secret_store: SecretStore) -> None:
    """Synchronize a local Azure bootstrap key into encrypted secret storage.

    ``AZURE_OPENAI_API_KEY`` is the authoritative source for a local backend
    bootstrap.  Runtime provider calls continue to read exclusively from the
    encrypted local SecretStore, so updating the environment value takes effect
    after the next backend startup without exposing it through the API.
    """

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    if not api_key:
        try:
            from dotenv import dotenv_values

            backend_env_file = Path(__file__).resolve().parents[2] / ".env"
            api_key = str(dotenv_values(backend_env_file).get("AZURE_OPENAI_API_KEY") or "").strip()
        except ImportError:
            return
    if api_key:
        await secret_store.set_secret(AZURE_OPENAI_API_KEY_REF, SecretStr(api_key))


def _updated_settings(settings: AppSettings, updates: dict[str, Any]) -> AppSettings:
    values = settings.model_dump()
    values.update(updates)
    if _llm_provider_changed(settings, updates) and "classification_mode" not in updates:
        candidate_settings = AppSettings(_env_file=None, **values)
        values["classification_mode"] = recommend_classification_mode(candidate_settings)
    return AppSettings(_env_file=None, **values)


def _llm_provider_changed(settings: AppSettings, updates: dict[str, Any]) -> bool:
    return "llm_provider" in updates and updates["llm_provider"] != settings.llm_provider


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


def _email_provider_response(provider: EmailProviderRegistration) -> EmailProviderConfigResponse:
    return EmailProviderConfigResponse(
        name=provider.name,
        display_name=provider.display_name,
        config_requirements=tuple(
            _config_requirement_response(item) for item in provider.config_requirements
        ),
        secret_requirements=tuple(
            _secret_requirement_response(item) for item in provider.secret_requirements
        ),
    )


def _llm_provider_response(provider: LLMProviderRegistration) -> LLMProviderConfigResponse:
    return LLMProviderConfigResponse(
        name=provider.name,
        display_name=provider.display_name,
        is_local=provider.is_local,
        config_requirements=tuple(
            _config_requirement_response(item) for item in provider.config_requirements
        ),
        secret_requirements=tuple(
            _secret_requirement_response(item) for item in provider.secret_requirements
        ),
    )
