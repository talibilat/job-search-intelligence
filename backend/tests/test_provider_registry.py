from __future__ import annotations

import pytest
from app.config import (
    AppSettings,
    ClassificationMode,
    EmailProviderName,
    LLMProviderName,
)
from app.providers import (
    ProviderConfigurationError,
    ProviderRegistry,
    ProviderRequirementEnforcement,
    provider_registry,
)
from app.security import SecretKind


def test_registry_includes_exact_phase_zero_provider_names() -> None:
    assert {provider.name for provider in provider_registry.email_providers()} == set(
        EmailProviderName
    )
    assert {provider.name for provider in provider_registry.llm_providers()} == set(LLMProviderName)


def test_registry_declares_gmail_oauth_secret_ref_without_secret_values() -> None:
    gmail = provider_registry.get_email_provider(EmailProviderName.GMAIL)

    assert gmail.display_name == "Gmail"
    assert [requirement.setting_name for requirement in gmail.config_requirements] == [
        "gmail_client_config_file",
        "gmail_scopes",
    ]
    assert {requirement.enforcement for requirement in gmail.config_requirements} == {
        ProviderRequirementEnforcement.DECLARATIVE,
    }
    assert len(gmail.secret_requirements) == 1
    secret_ref = gmail.secret_requirements[0].ref
    assert secret_ref.kind is SecretKind.OAUTH_TOKEN
    assert secret_ref.provider == "gmail"
    assert secret_ref.name == "refresh_token"
    assert gmail.secret_requirements[0].enforcement is ProviderRequirementEnforcement.DECLARATIVE
    assert "token-value" not in gmail.model_dump_json()


def test_registry_declares_ollama_as_local_without_api_key_secret() -> None:
    ollama = provider_registry.get_llm_provider(LLMProviderName.OLLAMA)

    assert ollama.display_name == "Ollama"
    assert ollama.is_local is True
    assert ollama.secret_requirements == ()
    assert [requirement.setting_name for requirement in ollama.config_requirements] == [
        "ollama_base_url",
        "ollama_chat_model",
        "ollama_embedding_model",
    ]
    assert {requirement.enforcement for requirement in ollama.config_requirements} == {
        ProviderRequirementEnforcement.SELECTION,
    }


def test_registry_declares_azure_openai_api_key_ref_without_secret_value() -> None:
    azure = provider_registry.get_llm_provider(LLMProviderName.AZURE_OPENAI)

    assert azure.display_name == "Azure OpenAI"
    assert azure.is_local is False
    assert [requirement.setting_name for requirement in azure.config_requirements] == [
        "azure_openai_endpoint",
        "azure_openai_api_version",
        "azure_openai_chat_deployment",
        "azure_openai_embedding_deployment",
    ]
    assert {requirement.enforcement for requirement in azure.config_requirements} == {
        ProviderRequirementEnforcement.SELECTION,
    }
    assert len(azure.secret_requirements) == 1
    secret_ref = azure.secret_requirements[0].ref
    assert secret_ref.kind is SecretKind.LLM_API_KEY
    assert secret_ref.provider == "azure_openai"
    assert secret_ref.name == "api_key"
    assert azure.secret_requirements[0].enforcement is ProviderRequirementEnforcement.DECLARATIVE
    assert "super-secret" not in azure.model_dump_json()


def test_default_settings_pass_provider_registry_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)

    settings = AppSettings(_env_file=None)

    provider_registry.validate_settings(settings)


def test_azure_openai_requires_non_secret_provider_metadata() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="",
        azure_openai_chat_deployment="",
        azure_openai_embedding_deployment="",
    )

    with pytest.raises(ProviderConfigurationError) as error:
        provider_registry.validate_settings(settings)

    assert error.value.provider_name == "azure_openai"
    assert error.value.missing_settings == (
        "azure_openai_endpoint",
        "azure_openai_chat_deployment",
        "azure_openai_embedding_deployment",
    )


def test_gmail_requirements_are_declarative_metadata_not_selection_validation() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.OLLAMA,
        classification_mode=ClassificationMode.LOCAL,
        gmail_client_config_file="   ",
    )

    provider_registry.validate_settings(settings)


def test_azure_openai_rejects_whitespace_only_provider_metadata() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="   ",
        azure_openai_chat_deployment="\t",
        azure_openai_embedding_deployment="\n",
    )

    with pytest.raises(ProviderConfigurationError) as error:
        provider_registry.validate_settings(settings)

    assert error.value.provider_name == "azure_openai"
    assert error.value.missing_settings == (
        "azure_openai_endpoint",
        "azure_openai_chat_deployment",
        "azure_openai_embedding_deployment",
    )


def test_azure_openai_rejects_local_classification_mode() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.LOCAL,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embeddings",
    )

    with pytest.raises(ProviderConfigurationError) as error:
        provider_registry.validate_settings(settings)

    assert error.value.provider_name == "azure_openai"
    assert error.value.message == "Azure OpenAI cannot be used with local classification mode."
    assert error.value.missing_settings == ()


def test_azure_openai_with_hybrid_mode_and_metadata_passes_validation() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embeddings",
    )

    provider_registry.validate_settings(settings)


def test_registry_can_be_instantiated_for_future_tests() -> None:
    registry = ProviderRegistry.default()

    assert registry.get_email_provider(EmailProviderName.GMAIL).name is EmailProviderName.GMAIL
    assert registry.get_llm_provider(LLMProviderName.OLLAMA).name is LLMProviderName.OLLAMA
