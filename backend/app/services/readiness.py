from __future__ import annotations

from typing import Protocol

from app.config import AppSettings, LLMProviderName
from app.models import ReadinessState
from app.models.provider_config import (
    CapabilityReadiness,
    ProviderReadinessResponse,
)
from app.providers import ProviderConfigurationError, ProviderRegistry
from app.providers.email import EmailConnection
from app.providers.llm import (
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProvider,
    LLMProviderError,
)
from app.security import (
    AZURE_OPENAI_API_KEY_REF,
    GMAIL_OAUTH_CLIENT_REF,
    SecretStore,
    SecretStoreError,
)
from app.services.llm_health import check_configured_llm_provider_health


class ConnectionReadinessReader(Protocol):
    def list_connections_metadata(self) -> list[EmailConnection]: ...


class ProviderReadinessService:
    """Report operational readiness without exposing credential material."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        registry: ProviderRegistry,
        connection_reader: ConnectionReadinessReader,
        secret_store: SecretStore,
        llm_provider: LLMProvider,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._connection_reader = connection_reader
        self._secret_store = secret_store
        self._llm_provider = llm_provider

    async def check(self) -> ProviderReadinessResponse:
        gmail = await self._gmail_readiness()
        classification, embedding = await self._llm_readiness()
        chat = _chat_readiness(classification, embedding)
        return ProviderReadinessResponse(
            ready_to_sync=gmail.state is ReadinessState.READY,
            ready_to_classify=classification.state is ReadinessState.READY,
            gmail_sync=gmail,
            classification_generation=classification,
            embedding_generation=embedding,
            chat_generation=chat,
        )

    async def _gmail_readiness(self) -> CapabilityReadiness:
        try:
            oauth_client = await self._secret_store.get_secret(GMAIL_OAUTH_CLIENT_REF)
        except SecretStoreError:
            return CapabilityReadiness(
                state=ReadinessState.UNAVAILABLE,
                message="Credential storage is unavailable.",
                action="Check the configured SecretStore and retry.",
            )
        if oauth_client is None and not self._settings.gmail_client_config_file.is_file():
            return CapabilityReadiness(
                state=ReadinessState.MISSING_CREDENTIAL,
                message="Google Desktop OAuth client JSON is required.",
                action="Enter the downloaded Desktop OAuth client JSON.",
            )
        connections = self._connection_reader.list_connections_metadata()
        if not connections:
            return CapabilityReadiness(
                state=ReadinessState.MISSING_CREDENTIAL,
                message="Gmail has not been authorized.",
                action="Connect Gmail with read-only access.",
            )
        connection = connections[0]
        if connection.reauth_required:
            return CapabilityReadiness(
                state=ReadinessState.REAUTH_REQUIRED,
                message="The Gmail connection requires authorization again.",
                action="Reconnect Gmail.",
            )
        try:
            connection_secret = await self._secret_store.get_secret(connection.credential_ref)
        except SecretStoreError:
            return CapabilityReadiness(
                state=ReadinessState.UNAVAILABLE,
                message="Credential storage is unavailable.",
                action="Check the configured SecretStore and retry.",
            )
        if connection_secret is None:
            return CapabilityReadiness(
                state=ReadinessState.MISSING_CREDENTIAL,
                message="The stored Gmail connection credential is missing.",
                action="Reconnect Gmail.",
            )
        return CapabilityReadiness(
            state=ReadinessState.READY,
            message="Gmail is authorized for read-only sync.",
        )

    async def _llm_readiness(self) -> tuple[CapabilityReadiness, CapabilityReadiness]:
        try:
            self._registry.validate_settings(self._settings)
        except ProviderConfigurationError as error:
            action = (
                f"Configure {', '.join(error.missing_settings)}."
                if error.missing_settings
                else "Choose compatible provider settings."
            )
            missing = CapabilityReadiness(
                state=ReadinessState.MISSING_CONFIG,
                message=error.message,
                action=action,
            )
            return missing, missing.model_copy()

        if self._settings.llm_provider is LLMProviderName.AZURE_OPENAI:
            try:
                api_key = await self._secret_store.get_secret(AZURE_OPENAI_API_KEY_REF)
            except SecretStoreError:
                unavailable = CapabilityReadiness(
                    state=ReadinessState.UNAVAILABLE,
                    message="Credential storage is unavailable.",
                    action="Check the configured SecretStore and retry.",
                )
                return unavailable, unavailable.model_copy()
            if api_key is None or not api_key.get_secret_value().strip():
                missing = CapabilityReadiness(
                    state=ReadinessState.MISSING_CREDENTIAL,
                    message="Azure OpenAI API key is required.",
                    action="Enter your Azure OpenAI API key.",
                )
                return missing, missing.model_copy()
            if not self._settings.azure_openai_embedding_deployment.strip():
                return await self._azure_classification_readiness_without_embeddings()

        try:
            response = await check_configured_llm_provider_health(
                self._settings,
                self._llm_provider,
                self._registry,
            )
        except LLMProviderError:
            unavailable = CapabilityReadiness(
                state=ReadinessState.UNAVAILABLE,
                message="The selected AI provider could not be reached.",
                action="Check the provider service and configured models, then retry.",
            )
            return unavailable, unavailable.model_copy()

        return (
            self._model_readiness(response.checks, LLMModelKind.CHAT, "classification"),
            self._model_readiness(response.checks, LLMModelKind.EMBEDDING, "embedding"),
        )

    async def _azure_classification_readiness_without_embeddings(
        self,
    ) -> tuple[CapabilityReadiness, CapabilityReadiness]:
        """Validate Azure chat classification without requiring later-phase embeddings."""

        try:
            await self._llm_provider.generate(
                LLMGenerationRequest(
                    messages=(LLMMessage(role=LLMMessageRole.USER, content="Health check."),),
                    model=self._settings.azure_openai_chat_deployment,
                    options=LLMGenerationOptions(max_output_tokens=64),
                )
            )
        except LLMProviderError:
            unavailable = CapabilityReadiness(
                state=ReadinessState.UNAVAILABLE,
                message="The selected AI provider could not be reached.",
                action="Check the provider service and configured chat deployment, then retry.",
            )
            return unavailable, unavailable.model_copy()
        return (
            CapabilityReadiness(
                state=ReadinessState.READY,
                message="Azure OpenAI chat classification is ready.",
            ),
            CapabilityReadiness(
                state=ReadinessState.MISSING_CONFIG,
                message="Azure OpenAI embedding deployment is not configured.",
                action="Configure an embedding deployment before using chat retrieval.",
            ),
        )

    @staticmethod
    def _model_readiness(
        checks: tuple[object, ...],
        kind: LLMModelKind,
        label: str,
    ) -> CapabilityReadiness:
        check = next((item for item in checks if getattr(item, "kind", None) is kind), None)
        if check is not None and getattr(check, "status", None) is LLMModelHealthStatus.AVAILABLE:
            return CapabilityReadiness(
                state=ReadinessState.READY,
                message=f"The configured {label} model is available.",
            )
        return CapabilityReadiness(
            state=ReadinessState.UNAVAILABLE,
            message=f"The configured {label} model is unavailable.",
            action="Start the provider or install/check the configured model, then retry.",
        )


def _chat_readiness(
    generation: CapabilityReadiness,
    embedding: CapabilityReadiness,
) -> CapabilityReadiness:
    if generation.state is ReadinessState.READY and embedding.state is ReadinessState.READY:
        return CapabilityReadiness(
            state=ReadinessState.READY,
            message="Grounded chat generation and semantic retrieval are available.",
        )
    blocking = generation if generation.state is not ReadinessState.READY else embedding
    return CapabilityReadiness(
        state=blocking.state,
        message="Chat requires both the configured chat and embedding models.",
        action=blocking.action,
    )
