"""Unit coverage for the provider-neutral HQ Batch STT boundary."""

import asyncio
from datetime import UTC, datetime

import pytest

from tbd.providers.stt import (
    BatchSTTInvalidResultError,
    BatchSTTRequest,
    BatchSTTSegment,
    DeterministicBatchSTTProvider,
    validate_batch_segments,
)

pytestmark = pytest.mark.unit


def test_deterministic_batch_provider_records_private_request_without_network() -> None:
    request = BatchSTTRequest(
        content=b"private recording",
        content_type="audio/webm",
        duration_ms=1000,
        deadline=datetime(2026, 7, 14, tzinfo=UTC),
    )
    expected = BatchSTTSegment(0, 500, 0, 500, "  첫 문장  ")
    provider = DeterministicBatchSTTProvider((expected,))

    results = asyncio.run(provider.transcribe(request))

    assert results == (expected,)
    assert provider.requests == [request]
    assert validate_batch_segments(results, duration_ms=1000) == (
        BatchSTTSegment(0, 500, 0, 500, "첫 문장"),
    )


@pytest.mark.parametrize(
    "segment",
    [
        BatchSTTSegment(0, 1001, 0, 1001, "범위 초과"),
        BatchSTTSegment(1, 0, 1, 0, "역순"),
        BatchSTTSegment(0, 1, 0, 1, "   "),
    ],
)
def test_batch_result_validation_rejects_unsafe_final_segments(segment: BatchSTTSegment) -> None:
    with pytest.raises(BatchSTTInvalidResultError):
        validate_batch_segments((segment,), duration_ms=1000)
