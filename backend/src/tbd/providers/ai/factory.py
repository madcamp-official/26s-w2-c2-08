"""One runtime selection point for AI providers used by the API and workers."""

from dataclasses import dataclass

from tbd.core.config import AIProviderRuntime, Settings
from tbd.providers.ai.clustering import QuestionClusteringProvider
from tbd.providers.ai.contracts import EmbeddingProvider, LLMProvider
from tbd.providers.ai.fake import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeQuestionClusteringProvider,
)
from tbd.providers.ai.ollama import OllamaEmbeddingProvider, OllamaLLMProvider


@dataclass(frozen=True, slots=True)
class AIProviders:
    """Provider set created once per process from one immutable Settings value."""

    llm: LLMProvider
    embedding: EmbeddingProvider
    question_clustering: QuestionClusteringProvider


def create_ai_providers(settings: Settings) -> AIProviders:
    """Build the configured LLM and embedding adapters without changing API contracts.

    Question clustering has its own structured provider boundary.  It remains a
    deterministic fake until its Mistral JSON adapter is implemented, but it is
    included here so every AI worker obtains its runtime dependencies from one
    place.
    """

    clustering = FakeQuestionClusteringProvider()
    if settings.ai_provider is AIProviderRuntime.FAKE:
        return AIProviders(
            llm=FakeLLMProvider(),
            embedding=FakeEmbeddingProvider(),
            question_clustering=clustering,
        )
    if settings.ai_provider is AIProviderRuntime.OLLAMA:
        return AIProviders(
            llm=OllamaLLMProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_llm_model,
            ),
            embedding=OllamaEmbeddingProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_embedding_model,
            ),
            question_clustering=clustering,
        )
    raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
