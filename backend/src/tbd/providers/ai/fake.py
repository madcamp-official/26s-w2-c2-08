"""Deterministic provider implementations for unit and integration tests."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta

from tbd.providers.ai.clustering import ClusteringInput, ClusterSuggestion
from tbd.providers.ai.contracts import (
    AIProviderError,
    EmbeddingRequest,
    EmbeddingResult,
    LLMGenerationRequest,
    LLMGenerationResult,
    invoke_provider,
)


@dataclass(frozen=True, slots=True)
class FakeProviderBehavior:
    """Optional deterministic delay or safe failure injected by a test."""

    delay: timedelta = timedelta()
    failure: AIProviderError | None = None

    def __post_init__(self) -> None:
        if self.delay.total_seconds() < 0:
            raise ValueError("fake provider delay must not be negative")


class FakeLLMProvider:
    """Return one stable completed result for each structured generation request."""

    def __init__(self, behavior: FakeProviderBehavior | None = None) -> None:
        self._behavior = behavior or FakeProviderBehavior()

    async def generate(
        self,
        request: LLMGenerationRequest,
        *,
        timeout: timedelta,
    ) -> LLMGenerationResult:
        return await invoke_provider(lambda: self._generate(request), timeout=timeout)

    async def _generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        await _apply_behavior(self._behavior)
        digest = hashlib.sha256(
            "\x1e".join(
                f"{message.role}\x1f{message.content}" for message in request.messages
            ).encode()
        ).hexdigest()[:16]
        return LLMGenerationResult(
            content=f"fake:{request.purpose}:{digest}",
            model_name="fake-llm-v1",
        )


class FakeEmbeddingProvider:
    """Return stable vectors without choosing the production embedding dimension."""

    def __init__(
        self,
        *,
        dimension: int = 768,
        behavior: FakeProviderBehavior | None = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("fake embedding dimension must be positive")
        self._dimension = dimension
        self._behavior = behavior or FakeProviderBehavior()

    async def embed(
        self,
        request: EmbeddingRequest,
        *,
        timeout: timedelta,
    ) -> EmbeddingResult:
        return await invoke_provider(lambda: self._embed(request), timeout=timeout)

    async def _embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        await _apply_behavior(self._behavior)
        return EmbeddingResult(
            vectors=tuple(
                _vector_for(request.purpose, text, self._dimension) for text in request.texts
            ),
            model_name="fake-embedding-v1",
        )


class FakeQuestionClusteringProvider:
    """Group Questions by a deterministic first Korean/word token for tests."""

    async def cluster(self, inputs: tuple[ClusteringInput, ...]) -> tuple[ClusterSuggestion, ...]:
        groups: dict[str, list[ClusteringInput]] = {}
        for item in inputs:
            token = _cluster_token(item.content)
            groups.setdefault(token, []).append(item)
        return tuple(
            ClusterSuggestion(
                representative=f"{token} 관련 질문",
                question_ids=tuple(item.question_id for item in grouped),
            )
            for token, grouped in sorted(groups.items())
        )


async def _apply_behavior(behavior: FakeProviderBehavior) -> None:
    if behavior.delay.total_seconds() > 0:
        await asyncio.sleep(behavior.delay.total_seconds())
    if behavior.failure is not None:
        raise behavior.failure


def _vector_for(purpose: str, text: str, dimension: int) -> tuple[float, ...]:
    digest = hashlib.sha256(f"{purpose}\x1f{text}".encode()).digest()
    return tuple((digest[index % len(digest)] / 127.5) - 1.0 for index in range(dimension))


def _cluster_token(content: str) -> str:
    match = re.search(r"[0-9A-Za-z가-힣]+", content)
    return match.group(0).casefold() if match else "기타"
