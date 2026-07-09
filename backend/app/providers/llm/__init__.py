"""Provider-neutral LLM strategy interface."""

from .errors import (
    LLMProviderError,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from .ollama import OllamaLLMProvider
from .provider import LLMEmbeddingProvider, LLMProvider
from .types import (
    LLMEmbedding,
    LLMEmbeddingRequest,
    LLMEmbeddingResponse,
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMModelHealthCheck,
    LLMModelHealthStatus,
    LLMModelKind,
    LLMProviderHealthCheckRequest,
    LLMProviderHealthCheckResponse,
    LLMResponseFormat,
    LLMTokenUsage,
)

__all__ = [
    "LLMFinishReason",
    "LLMEmbedding",
    "LLMEmbeddingRequest",
    "LLMEmbeddingResponse",
    "LLMGenerationOptions",
    "LLMGenerationRequest",
    "LLMGenerationResponse",
    "LLMModelHealthCheck",
    "LLMModelHealthStatus",
    "LLMModelKind",
    "LLMMessage",
    "LLMMessageRole",
    "LLMEmbeddingProvider",
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderRequestError",
    "LLMProviderResponseError",
    "LLMProviderHealthCheckRequest",
    "LLMProviderHealthCheckResponse",
    "LLMProviderTimeoutError",
    "LLMProviderUnavailableError",
    "LLMResponseFormat",
    "LLMTokenUsage",
    "OllamaLLMProvider",
]
