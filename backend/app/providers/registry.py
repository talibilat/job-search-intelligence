from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.config import AppSettings, ClassificationMode, EmailProviderName, LLMProviderName
from app.providers.llm.ollama import is_local_ollama_base_url
from app.security import GMAIL_OAUTH_CLIENT_REF, SecretKind, SecretRef


class ProviderRequirementEnforcement(StrEnum):
    DECLARATIVE = "declarative"
    SELECTION = "selection"


class ProviderConfigRequirement(BaseModel):
    """Non-secret setting required by a provider."""

    model_config = ConfigDict(frozen=True)

    setting_name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    required: bool = True
    enforcement: ProviderRequirementEnforcement = ProviderRequirementEnforcement.SELECTION


class ProviderSecretRequirement(BaseModel):
    """Secret-store reference required by a provider."""

    model_config = ConfigDict(frozen=True)

    ref: SecretRef
    label: str = Field(min_length=1)
    required: bool = True
    enforcement: ProviderRequirementEnforcement = ProviderRequirementEnforcement.DECLARATIVE


class EmailProviderRegistration(BaseModel):
    """Registry metadata for a supported email provider."""

    model_config = ConfigDict(frozen=True)

    name: EmailProviderName
    display_name: str = Field(min_length=1)
    config_requirements: tuple[ProviderConfigRequirement, ...] = ()
    secret_requirements: tuple[ProviderSecretRequirement, ...] = ()


class LLMProviderRegistration(BaseModel):
    """Registry metadata for a supported LLM provider."""

    model_config = ConfigDict(frozen=True)

    name: LLMProviderName
    display_name: str = Field(min_length=1)
    is_local: bool
    config_requirements: tuple[ProviderConfigRequirement, ...] = ()
    secret_requirements: tuple[ProviderSecretRequirement, ...] = ()


class ProviderConfigurationError(ValueError):
    """Raised when selected provider settings are incomplete or incompatible."""

    def __init__(
        self,
        *,
        provider_name: str,
        message: str,
        missing_settings: Sequence[str] = (),
    ) -> None:
        self.provider_name = provider_name
        self.message = message
        self.missing_settings = tuple(missing_settings)
        super().__init__(message)


class ProviderRegistry:
    """Typed registry for supported provider metadata and settings validation."""

    def __init__(
        self,
        *,
        email_providers: Iterable[EmailProviderRegistration],
        llm_providers: Iterable[LLMProviderRegistration],
    ) -> None:
        self._email_providers: dict[EmailProviderName, EmailProviderRegistration] = {
            provider.name: provider for provider in email_providers
        }
        self._llm_providers: dict[LLMProviderName, LLMProviderRegistration] = {
            provider.name: provider for provider in llm_providers
        }

        email_names = set(self._email_providers)
        llm_names = set(self._llm_providers)
        if email_names != set(EmailProviderName):
            raise ValueError("email provider registry must match EmailProviderName")
        if llm_names != set(LLMProviderName):
            raise ValueError("LLM provider registry must match LLMProviderName")

    @classmethod
    def default(cls) -> ProviderRegistry:
        return cls(
            email_providers=(
                EmailProviderRegistration(
                    name=EmailProviderName.GMAIL,
                    display_name="Gmail",
                    config_requirements=(
                        ProviderConfigRequirement(
                            setting_name="gmail_scopes",
                            label="Gmail OAuth scopes",
                            enforcement=ProviderRequirementEnforcement.DECLARATIVE,
                        ),
                    ),
                    secret_requirements=(
                        ProviderSecretRequirement(
                            ref=GMAIL_OAUTH_CLIENT_REF,
                            label="Google Desktop OAuth client JSON",
                        ),
                        ProviderSecretRequirement(
                            ref=SecretRef(
                                kind=SecretKind.OAUTH_TOKEN,
                                provider="gmail",
                                name="refresh_token",
                            ),
                            label="Gmail OAuth refresh token",
                        ),
                    ),
                ),
            ),
            llm_providers=(
                LLMProviderRegistration(
                    name=LLMProviderName.AZURE_OPENAI,
                    display_name="Azure OpenAI",
                    is_local=False,
                    config_requirements=(
                        ProviderConfigRequirement(
                            setting_name="azure_openai_endpoint",
                            label="Azure OpenAI endpoint",
                        ),
                        ProviderConfigRequirement(
                            setting_name="azure_openai_api_version",
                            label="Azure OpenAI API version",
                        ),
                        ProviderConfigRequirement(
                            setting_name="azure_openai_chat_deployment",
                            label="Azure OpenAI chat deployment",
                        ),
                        ProviderConfigRequirement(
                            setting_name="azure_openai_embedding_deployment",
                            label="Azure OpenAI embedding deployment",
                        ),
                    ),
                    secret_requirements=(
                        ProviderSecretRequirement(
                            ref=SecretRef(
                                kind=SecretKind.LLM_API_KEY,
                                provider="azure_openai",
                                name="api_key",
                            ),
                            label="Azure OpenAI API key",
                        ),
                    ),
                ),
                LLMProviderRegistration(
                    name=LLMProviderName.OLLAMA,
                    display_name="Ollama",
                    is_local=True,
                    config_requirements=(
                        ProviderConfigRequirement(
                            setting_name="ollama_base_url",
                            label="Ollama base URL",
                        ),
                        ProviderConfigRequirement(
                            setting_name="ollama_chat_model",
                            label="Ollama chat model",
                        ),
                        ProviderConfigRequirement(
                            setting_name="ollama_embedding_model",
                            label="Ollama embedding model",
                        ),
                    ),
                ),
            ),
        )

    def email_providers(self) -> tuple[EmailProviderRegistration, ...]:
        return tuple(self._email_providers.values())

    def llm_providers(self) -> tuple[LLMProviderRegistration, ...]:
        return tuple(self._llm_providers.values())

    def get_email_provider(self, name: EmailProviderName) -> EmailProviderRegistration:
        return self._email_providers[name]

    def get_llm_provider(self, name: LLMProviderName) -> LLMProviderRegistration:
        return self._llm_providers[name]

    @staticmethod
    def _is_missing_required_setting(value: object) -> bool:
        if isinstance(value, str):
            return not value.strip()

        return not value

    def validate_settings(self, settings: AppSettings) -> None:
        self.get_email_provider(settings.email_provider)
        llm_provider = self.get_llm_provider(settings.llm_provider)
        missing_settings = tuple(
            requirement.setting_name
            for requirement in llm_provider.config_requirements
            if requirement.required
            and requirement.enforcement is ProviderRequirementEnforcement.SELECTION
            and self._is_missing_required_setting(getattr(settings, requirement.setting_name))
        )

        if missing_settings:
            raise ProviderConfigurationError(
                provider_name=settings.llm_provider.value,
                message="Selected LLM provider is missing required non-secret settings.",
                missing_settings=missing_settings,
            )

        if (
            settings.llm_provider is LLMProviderName.AZURE_OPENAI
            and settings.classification_mode is ClassificationMode.LOCAL
        ):
            raise ProviderConfigurationError(
                provider_name=settings.llm_provider.value,
                message="Azure OpenAI cannot be used with local classification mode.",
            )

        if settings.llm_provider is LLMProviderName.OLLAMA and not is_local_ollama_base_url(
            settings.ollama_base_url
        ):
            raise ProviderConfigurationError(
                provider_name=settings.llm_provider.value,
                message="Ollama base URL must point to a local host.",
                missing_settings=("ollama_base_url",),
            )


provider_registry = ProviderRegistry.default()
