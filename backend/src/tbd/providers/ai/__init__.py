"""Provider-neutral LLM and embedding contracts used by later AI features."""

from tbd.providers.ai.clustering import (
    ClusteringInput,
    ClusterSuggestion,
    QuestionClusteringProvider,
)
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
from tbd.providers.ai.factory import AIProviders, create_ai_providers
from tbd.providers.ai.fake import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeProviderBehavior,
    FakeQuestionClusteringProvider,
)
from tbd.providers.ai.ollama import (
    OllamaEmbeddingProvider,
    OllamaLLMProvider,
    OllamaQuestionClusteringProvider,
)

__all__ = [
    "AIProviderError",
    "AIProviders",
    "EmbeddingProvider",
    "EmbeddingRequest",
    "EmbeddingResult",
    "FakeEmbeddingProvider",
    "FakeLLMProvider",
    "FakeProviderBehavior",
    "FakeQuestionClusteringProvider",
    "ClusterSuggestion",
    "ClusteringInput",
    "LLMGenerationRequest",
    "LLMGenerationResult",
    "LLMMessage",
    "LLMProvider",
    "OllamaEmbeddingProvider",
    "OllamaLLMProvider",
    "OllamaQuestionClusteringProvider",
    "QuestionClusteringProvider",
    "ProviderErrorCode",
    "ProviderInvalidResponseError",
    "ProviderRateLimitedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "invoke_provider",
    "create_ai_providers",
]
