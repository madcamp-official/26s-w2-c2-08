"""Unit tests for the provider-neutral LLM and embedding boundaries."""

import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

from tbd.providers.ai import (
    EmbeddingRequest,
    EmbeddingResult,
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeProviderBehavior,
    LLMGenerationRequest,
    LLMMessage,
    OllamaEmbeddingProvider,
    OllamaLLMProvider,
    OllamaQuestionClusteringProvider,
    ProviderErrorCode,
    ProviderInvalidResponseError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    invoke_provider,
)
from tbd.providers.ai.clustering import ClusteringInput

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


def test_ollama_llm_returns_one_completed_chat_response() -> None:
    """The adapter sends one non-streaming request and projects only safe output."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        assert json.loads(request.content) == {
            "model": "mistral-small3.2:24b",
            "messages": [{"role": "user", "content": "질문 초안"}],
            "stream": False,
        }
        return httpx.Response(
            200,
            json={
                "model": "mistral-small3.2:24b",
                "done": True,
                "message": {"role": "assistant", "content": "정리된 질문입니다."},
            },
        )

    async def exercise() -> None:
        provider = OllamaLLMProvider(
            base_url="http://ollama.local:11434/",
            model="mistral-small3.2:24b",
            transport=httpx.MockTransport(handler),
        )
        result = await provider.generate(_generation_request(), timeout=timedelta(seconds=1))

        assert result.content == "정리된 질문입니다."
        assert result.model_name == "mistral-small3.2:24b"

    asyncio.run(exercise())


def test_ollama_embedding_preserves_input_order() -> None:
    """The adapter returns vectors in exactly the order accepted by the contract."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        assert json.loads(request.content) == {
            "model": "embeddinggemma",
            "input": ["첫 번째", "두 번째"],
        }
        return httpx.Response(
            200,
            json={
                "model": "embeddinggemma:300m",
                "embeddings": [[0.1, -0.2], [0.3, 0.4]],
            },
        )

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://ollama.local:11434",
            model="embeddinggemma",
            transport=httpx.MockTransport(handler),
        )
        result = await provider.embed(
            EmbeddingRequest(purpose="knowledge-indexing-v1", texts=("첫 번째", "두 번째")),
            timeout=timedelta(seconds=1),
        )

        assert result.vectors == ((0.1, -0.2), (0.3, 0.4))
        assert result.model_name == "embeddinggemma:300m"

    asyncio.run(exercise())


def test_ollama_clustering_requests_semantic_groups_instead_of_singletons() -> None:
    """The production prompt asks the model to merge questions answerable together."""

    first_id, second_id = uuid4(), uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        assert "Merge paraphrases and questions that can be answered together" in prompt
        assert "create a singleton only when" in prompt
        return httpx.Response(
            200,
            json={
                "model": "mistral-small3.2:24b",
                "done": True,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "clusters": [
                                {
                                    "representative": "18번 문제의 핵심 개념과 풀이 방법은 무엇인가요?",
                                    "question_ids": [str(first_id), str(second_id)],
                                }
                            ]
                        },
                        ensure_ascii=False,
                    ),
                },
            },
        )

    async def exercise() -> None:
        provider = OllamaQuestionClusteringProvider(
            base_url="http://ollama.local:11434",
            model="mistral-small3.2:24b",
            timeout=timedelta(seconds=90),
            transport=httpx.MockTransport(handler),
        )
        result = await provider.cluster(
            (
                ClusteringInput(first_id, "18번 문제는 어떻게 풀어요?"),
                ClusteringInput(second_id, "18번 문제의 핵심 개념은 무엇인가요?"),
            )
        )
        assert result[0].question_ids == (first_id, second_id)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("status_code", "error_type", "error_code"),
    [
        (429, ProviderRateLimitedError, ProviderErrorCode.RATE_LIMITED),
        (503, ProviderUnavailableError, ProviderErrorCode.UNAVAILABLE),
        (400, ProviderInvalidResponseError, ProviderErrorCode.INVALID_RESPONSE),
    ],
)
def test_ollama_http_failures_are_safe_and_classified(
    status_code: int,
    error_type: type[Exception],
    error_code: ProviderErrorCode,
) -> None:
    """HTTP status bodies never escape the provider boundary."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider says private details")

    async def exercise() -> None:
        provider = OllamaLLMProvider(
            base_url="http://ollama.local:11434",
            model="mistral-small3.2:24b",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(error_type) as raised:
            await provider.generate(_generation_request(), timeout=timedelta(seconds=1))

        assert isinstance(
            raised.value,
            (ProviderRateLimitedError, ProviderUnavailableError, ProviderInvalidResponseError),
        )
        assert raised.value.code is error_code
        assert "private details" not in str(raised.value)

    asyncio.run(exercise())


def test_ollama_transport_timeout_and_malformed_payloads_are_safe() -> None:
    """Connection failure, deadline expiry, and invalid JSON become contract errors."""

    async def connection_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private connection failure", request=request)

    async def timeout_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout")

    async def malformed_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done": True, "message": {"content": ""}})

    async def exercise() -> None:
        connection_provider = OllamaLLMProvider(
            base_url="http://ollama.local:11434",
            model="mistral-small3.2:24b",
            transport=httpx.MockTransport(connection_handler),
        )
        with pytest.raises(ProviderUnavailableError) as connection_raised:
            await connection_provider.generate(_generation_request(), timeout=timedelta(seconds=1))
        assert "private connection failure" not in str(connection_raised.value)

        timeout_provider = OllamaLLMProvider(
            base_url="http://ollama.local:11434",
            model="mistral-small3.2:24b",
            transport=httpx.MockTransport(timeout_handler),
        )
        with pytest.raises(ProviderTimeoutError):
            await timeout_provider.generate(_generation_request(), timeout=timedelta(seconds=1))

        malformed_provider = OllamaLLMProvider(
            base_url="http://ollama.local:11434",
            model="mistral-small3.2:24b",
            transport=httpx.MockTransport(malformed_handler),
        )
        with pytest.raises(ProviderInvalidResponseError):
            await malformed_provider.generate(_generation_request(), timeout=timedelta(seconds=1))

    asyncio.run(exercise())
