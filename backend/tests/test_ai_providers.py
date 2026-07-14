"""Unit tests for the provider-neutral LLM and embedding boundaries."""

import asyncio
from datetime import timedelta

import pytest

from tbd.providers.ai import (
    EmbeddingRequest,
    EmbeddingResult,
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeProviderBehavior,
    LLMGenerationRequest,
    LLMMessage,
    ProviderErrorCode,
    ProviderInvalidResponseError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    invoke_provider,
)

pytestmark = pytest.mark.unit


def _generation_request() -> LLMGenerationRequest:
    return LLMGenerationRequest(
        purpose="QUESTION_DRAFT_HELP",
        messages=(LLMMessage(role="user", content="질문 초안"),),
        prompt_version="question-draft-v1",
    )


def test_fake_llm_is_deterministic_without_returning_input_text() -> None:
    """The fake is reproducible without treating a caller prompt as public output."""

    async def exercise() -> None:
        provider = FakeLLMProvider()
        request = _generation_request()

        first = await provider.generate(request, timeout=timedelta(seconds=1))
        second = await provider.generate(request, timeout=timedelta(seconds=1))

        assert first == second
        assert first.model_name == "fake-llm-v1"
        assert "질문 초안" not in first.content

    asyncio.run(exercise())


def test_fake_embedding_preserves_request_order_with_configured_test_dimension() -> None:
    """A fake dimension is test-only and each vector follows the input order."""

    async def exercise() -> None:
        provider = FakeEmbeddingProvider(dimension=3)
        request = EmbeddingRequest(
            purpose="KNOWLEDGE_CHUNK",
            texts=("첫 번째 문장", "두 번째 문장"),
        )

        first = await provider.embed(request, timeout=timedelta(seconds=1))
        second = await provider.embed(request, timeout=timedelta(seconds=1))

        assert first == second
        assert first.dimension == 3
        assert len(first.vectors) == len(request.texts)
        assert first.vectors[0] != first.vectors[1]

    asyncio.run(exercise())


def test_fake_provider_preserves_safe_retryable_failures() -> None:
    """An adapter-provided safe error remains available to the caller unchanged."""

    async def exercise() -> None:
        provider = FakeLLMProvider(FakeProviderBehavior(failure=ProviderRateLimitedError()))

        with pytest.raises(ProviderRateLimitedError) as raised:
            await provider.generate(_generation_request(), timeout=timedelta(seconds=1))

        assert raised.value.code is ProviderErrorCode.RATE_LIMITED
        assert raised.value.retryable is True
        assert str(raised.value) == "AI provider request failed."

    asyncio.run(exercise())


def test_provider_timeout_is_normalized_without_provider_details() -> None:
    """Deadline expiry has one safe retryable error regardless of fake implementation."""

    async def exercise() -> None:
        provider = FakeLLMProvider(FakeProviderBehavior(delay=timedelta(milliseconds=50)))

        with pytest.raises(ProviderTimeoutError) as raised:
            await provider.generate(_generation_request(), timeout=timedelta(milliseconds=1))

        assert raised.value.code is ProviderErrorCode.TIMEOUT
        assert raised.value.retryable is True
        assert str(raised.value) == "AI provider request failed."

    asyncio.run(exercise())


def test_provider_cancellation_propagates_to_the_caller() -> None:
    """A caller shutdown must not become a retryable provider failure."""

    async def exercise() -> None:
        provider = FakeEmbeddingProvider(behavior=FakeProviderBehavior(delay=timedelta(seconds=1)))
        task = asyncio.create_task(
            provider.embed(
                EmbeddingRequest(purpose="KNOWLEDGE_CHUNK", texts=("문장",)),
                timeout=timedelta(seconds=5),
            )
        )
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())


def test_unknown_provider_exception_is_redacted_as_unavailable() -> None:
    """Unexpected implementation exceptions cannot expose a prompt or provider response."""

    async def operation() -> str:
        raise RuntimeError("provider response for private prompt")

    async def exercise() -> None:
        with pytest.raises(ProviderUnavailableError) as raised:
            await invoke_provider(operation, timeout=timedelta(seconds=1))

        assert raised.value.code is ProviderErrorCode.UNAVAILABLE
        assert raised.value.retryable is True
        assert str(raised.value) == "AI provider request failed."
        assert "private prompt" not in str(raised.value)

    asyncio.run(exercise())


def test_invalid_provider_result_contract_is_non_retryable() -> None:
    """Malformed vector shape is not mistaken for a temporary provider outage."""

    with pytest.raises(ValueError, match="share one dimension"):
        EmbeddingResult(vectors=((0.0,), (1.0, 2.0)))

    error = ProviderInvalidResponseError()
    assert error.code is ProviderErrorCode.INVALID_RESPONSE
    assert error.retryable is False
