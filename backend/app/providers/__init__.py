"""Provider registry and adapter seams."""

from .registry import (
    EmailProviderRegistration,
    LLMProviderRegistration,
    ProviderConfigRequirement,
    ProviderConfigurationError,
    ProviderRegistry,
    ProviderRequirementEnforcement,
    ProviderSecretRequirement,
    provider_registry,
)

__all__ = [
    "EmailProviderRegistration",
    "LLMProviderRegistration",
    "ProviderConfigRequirement",
    "ProviderConfigurationError",
    "ProviderRegistry",
    "ProviderRequirementEnforcement",
    "ProviderSecretRequirement",
    "provider_registry",
]
