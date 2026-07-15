"""Ollama HTTP adapters behind the provider-neutral AI contracts.

The adapters deliberately return only completed responses.  They do not expose
Ollama response payloads, prompts, or transport failures outside this module.
Runtime selection remains separate from these transport adapters so tests and
local development can continue to use deterministic fakes by default.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from tbd.providers.ai.clustering import ClusteringInput, ClusterSuggestion
from tbd.providers.ai.contracts import (
    EmbeddingRequest,
    EmbeddingResult,
    LLMGenerationRequest,
    LLMGenerationResult,
    ProviderInvalidResponseError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    invoke_provider,
)

CLUSTERING_TIMEOUT = timedelta(seconds=30)
_CLUSTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "representative": {"type": "string"},
                    "question_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["representative", "question_ids"],
            },
        }
    },
    "required": ["clusters"],
}


class OllamaLLMProvider:
    """Call one locally hosted Ollama chat model without streaming deltas."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._model = _require_non_empty(model, field_name="model")
        self._transport = transport

    async def generate(
        self,
        request: LLMGenerationRequest,
        *,
        timeout: timedelta,
    ) -> LLMGenerationResult:
        """Return one completed `/api/chat` result before the caller deadline."""

        return await invoke_provider(
            lambda: self._generate(request, timeout=timeout),
            timeout=timeout,
        )

    async def _generate(
        self,
        request: LLMGenerationRequest,
        *,
        timeout: timedelta,
    ) -> LLMGenerationResult:
        payload = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "stream": False,
        }
        data = await _post_json(
            base_url=self._base_url,
            path="/api/chat",
            payload=payload,
            timeout=timeout,
            transport=self._transport,
        )
        if data.get("done") is not True:
            raise ProviderInvalidResponseError
        message = data.get("message")
        if not isinstance(message, Mapping):
            raise ProviderInvalidResponseError
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderInvalidResponseError
        return LLMGenerationResult(
            content=content.strip(),
            model_name=_response_model_name(data, fallback=self._model),
        )


class OllamaEmbeddingProvider:
    """Call one locally hosted Ollama embedding model without exposing payloads."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._model = _require_non_empty(model, field_name="model")
        self._transport = transport

    async def embed(
        self,
        request: EmbeddingRequest,
        *,
        timeout: timedelta,
    ) -> EmbeddingResult:
        """Return vectors in request order from Ollama's `/api/embed` endpoint."""

        return await invoke_provider(
            lambda: self._embed(request, timeout=timeout),
            timeout=timeout,
        )

    async def _embed(
        self,
        request: EmbeddingRequest,
        *,
        timeout: timedelta,
    ) -> EmbeddingResult:
        data = await _post_json(
            base_url=self._base_url,
            path="/api/embed",
            payload={"model": self._model, "input": list(request.texts)},
            timeout=timeout,
            transport=self._transport,
        )
        raw_vectors = data.get("embeddings")
        if not isinstance(raw_vectors, list) or len(raw_vectors) != len(request.texts):
            raise ProviderInvalidResponseError
        vectors: list[tuple[float, ...]] = []
        for raw_vector in raw_vectors:
            if not isinstance(raw_vector, list) or not raw_vector:
                raise ProviderInvalidResponseError
            vector: list[float] = []
            for value in raw_vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ProviderInvalidResponseError
                normalized = float(value)
                if not math.isfinite(normalized):
                    raise ProviderInvalidResponseError
                vector.append(normalized)
            vectors.append(tuple(vector))
        try:
            return EmbeddingResult(
                vectors=tuple(vectors),
                model_name=_response_model_name(data, fallback=self._model),
            )
        except ValueError as exc:
            raise ProviderInvalidResponseError from exc


class OllamaQuestionClusteringProvider:
    """Request a complete Question partition as an Ollama structured output."""

    def __init__(
        self, *, base_url: str, model: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._model = _require_non_empty(model, field_name="model")
        self._transport = transport

    async def cluster(self, inputs: tuple[ClusteringInput, ...]) -> tuple[ClusterSuggestion, ...]:
        if not inputs:
            return ()
        return await invoke_provider(lambda: self._cluster(inputs), timeout=CLUSTERING_TIMEOUT)

    async def _cluster(self, inputs: tuple[ClusteringInput, ...]) -> tuple[ClusterSuggestion, ...]:
        question_lines = "\n".join(f"- id={item.question_id}: {item.content}" for item in inputs)
        prompt = (
            "Group semantically similar anonymous lecture questions. Return every supplied id "
            "exactly once; do not invent ids. Write each representative in Korean, under 300 "
            "characters. Return only this JSON schema: "
            f"{json.dumps(_CLUSTER_SCHEMA, ensure_ascii=False)}\nQuestions:\n{question_lines}"
        )
        data = await _post_json(
            base_url=self._base_url,
            path="/api/chat",
            payload={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "format": _CLUSTER_SCHEMA,
                "options": {"temperature": 0},
                "stream": False,
            },
            timeout=CLUSTERING_TIMEOUT,
            transport=self._transport,
        )
        if data.get("done") is not True or not isinstance(data.get("message"), Mapping):
            raise ProviderInvalidResponseError
        content = data["message"].get("content")
        if not isinstance(content, str):
            raise ProviderInvalidResponseError
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderInvalidResponseError from exc
        if not isinstance(parsed, Mapping) or not isinstance(parsed.get("clusters"), list):
            raise ProviderInvalidResponseError
        suggestions: list[ClusterSuggestion] = []
        for raw in parsed["clusters"]:
            if not isinstance(raw, Mapping):
                raise ProviderInvalidResponseError
            representative = raw.get("representative")
            raw_ids = raw.get("question_ids")
            if (
                not isinstance(representative, str)
                or not representative.strip()
                or len(representative.strip()) > 300
                or not isinstance(raw_ids, list)
                or not raw_ids
            ):
                raise ProviderInvalidResponseError
            try:
                question_ids = tuple(UUID(value) for value in raw_ids if isinstance(value, str))
            except ValueError as exc:
                raise ProviderInvalidResponseError from exc
            if len(question_ids) != len(raw_ids):
                raise ProviderInvalidResponseError
            suggestions.append(
                ClusterSuggestion(representative=representative.strip(), question_ids=question_ids)
            )
        return tuple(suggestions)


async def _post_json(
    *,
    base_url: str,
    path: str,
    payload: dict[str, Any],
    timeout: timedelta,
    transport: httpx.AsyncBaseTransport | None,
) -> Mapping[str, Any]:
    """Make one bounded local HTTP request and normalize transport failures."""

    timeout_seconds = timeout.total_seconds()
    if timeout_seconds <= 0:
        raise ValueError("provider timeout must be positive")
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        ) as client:
            response = await client.post(path, json=payload)
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError from exc
    except httpx.RequestError as exc:
        raise ProviderUnavailableError from exc

    if response.status_code == 429:
        raise ProviderRateLimitedError
    if response.status_code >= 500 or response.status_code == 404:
        raise ProviderUnavailableError
    if response.is_error:
        raise ProviderInvalidResponseError
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderInvalidResponseError from exc
    if not isinstance(data, Mapping):
        raise ProviderInvalidResponseError
    return data


def _normalize_base_url(base_url: str) -> str:
    """Accept one absolute HTTP(S) Ollama origin without path/query credentials."""

    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url must be an exact HTTP(S) origin")
    return normalized


def _require_non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _response_model_name(data: Mapping[str, Any], *, fallback: str) -> str:
    """Keep a model label when it is safe, never requiring provider metadata."""

    model_name = data.get("model")
    return model_name.strip() if isinstance(model_name, str) and model_name.strip() else fallback
