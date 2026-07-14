"""Provider-neutral LLM and embedding contracts used by later AI features."""

from tbd.providers.ai.contracts import (
    AIProviderError,
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
    LLMGenerationRequest,
    LLMGenerationResult,
    LLMMessage,
    LLMProvider,
    ProviderErrorCode,
    ProviderInvalidResponseError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    invoke_provider,
)
from tbd.providers.ai.fake import FakeEmbeddingProvider, FakeLLMProvider, FakeProviderBehavior

__all__ = [
    "AIProviderError",
    "EmbeddingProvider",
    "EmbeddingRequest",
    "EmbeddingResult",
    "FakeEmbeddingProvider",
    "FakeLLMProvider",
    "FakeProviderBehavior",
    "LLMGenerationRequest",
    "LLMGenerationResult",
    "LLMMessage",
    "LLMProvider",
    "ProviderErrorCode",
    "ProviderInvalidResponseError",
    "ProviderRateLimitedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "invoke_provider",
]
