"""Provider-neutral asynchronous contracts for LLM and embedding calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ProviderErrorCode(StrEnum):
    """Safe provider failure codes that callers may persist or project."""

    TIMEOUT = "PROVIDER_TIMEOUT"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"


class AIProviderError(Exception):
    """Base error that intentionally omits prompts, secrets, and provider details."""

    def __init__(
        self,
        code: ProviderErrorCode,
        *,
        retryable: bool,
        message: str = "AI provider request failed.",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderTimeoutError(AIProviderError):
    """Raised when a provider call did not finish before its caller deadline."""

    def __init__(self) -> None:
        super().__init__(ProviderErrorCode.TIMEOUT, retryable=True)


class ProviderUnavailableError(AIProviderError):
    """Raised when the configured runtime cannot serve a request."""

    def __init__(self) -> None:
        super().__init__(ProviderErrorCode.UNAVAILABLE, retryable=True)


class ProviderRateLimitedError(AIProviderError):
    """Raised when a provider rejects a request because of a temporary limit."""

    def __init__(self) -> None:
        super().__init__(ProviderErrorCode.RATE_LIMITED, retryable=True)


class ProviderInvalidResponseError(AIProviderError):
    """Raised when a provider response cannot satisfy the internal contract."""

    def __init__(self) -> None:
        super().__init__(ProviderErrorCode.INVALID_RESPONSE, retryable=False)


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """One internal LLM turn; content remains private to the caller's boundary."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.content:
            raise ValueError("LLM messages require a non-empty role and content")


@dataclass(frozen=True, slots=True)
class LLMGenerationRequest:
    """A structured LLM generation request without provider-specific options."""

    purpose: str
    messages: tuple[LLMMessage, ...]
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        if not self.purpose.strip() or not self.messages:
            raise ValueError("LLM generation requires a purpose and at least one message")
        if self.prompt_version is not None and not self.prompt_version.strip():
            raise ValueError("prompt_version must be omitted or non-empty")


@dataclass(frozen=True, slots=True)
class LLMGenerationResult:
    """A completed provider result; streaming deltas are not represented here."""

    content: str
    model_name: str | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("LLM generation results must contain content")


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    """Text values to vectorize while preserving their caller-supplied order."""

    purpose: str
    texts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.purpose.strip() or not self.texts or any(not text for text in self.texts):
            raise ValueError("Embedding requests require a purpose and non-empty texts")


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors returned in the same order as :class:`EmbeddingRequest.texts`."""

    vectors: tuple[tuple[float, ...], ...]
    model_name: str | None = None

    def __post_init__(self) -> None:
        if not self.vectors or any(not vector for vector in self.vectors):
            raise ValueError("Embedding results require at least one non-empty vector")
        dimensions = {len(vector) for vector in self.vectors}
        if len(dimensions) != 1:
            raise ValueError("Embedding result vectors must share one dimension")

    @property
    def dimension(self) -> int:
        """Return the observed dimension without making it a product decision."""

        return len(self.vectors[0])


@runtime_checkable
class LLMProvider(Protocol):
    """Asynchronous LLM boundary owned by application services and workers."""

    async def generate(
        self,
        request: LLMGenerationRequest,
        *,
        timeout: timedelta,
    ) -> LLMGenerationResult:
        """Generate one completed response before the caller deadline."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Asynchronous embedding boundary owned by application services and workers."""

    async def embed(
        self,
        request: EmbeddingRequest,
        *,
        timeout: timedelta,
    ) -> EmbeddingResult:
        """Return vectors in the same order as the requested text values."""


async def invoke_provider[ResultT](
    operation: Callable[[], Awaitable[ResultT]],
    *,
    timeout: timedelta,
) -> ResultT:
    """Normalize timeout and unknown provider failures without leaking raw details."""

    timeout_seconds = timeout.total_seconds()
    if timeout_seconds <= 0:
        raise ValueError("provider timeout must be positive")

    try:
        return await asyncio.wait_for(operation(), timeout=timeout_seconds)
    except asyncio.CancelledError:
        raise
    except AIProviderError:
        raise
    except TimeoutError:
        raise ProviderTimeoutError from None
    except Exception:
        raise ProviderUnavailableError from None
