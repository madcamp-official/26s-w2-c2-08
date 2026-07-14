"""Streaming STT abstractions owned by the live audio boundary."""

from tbd.providers.stt.batch import (
    BatchSTTError,
    BatchSTTInvalidResultError,
    BatchSTTProvider,
    BatchSTTRequest,
    BatchSTTSegment,
    BatchSTTTimeoutError,
    BatchSTTUnavailableError,
    DeterministicBatchSTTProvider,
    UnavailableBatchSTTProvider,
    validate_batch_segments,
)
from tbd.providers.stt.streaming import (
    DeterministicStreamingSTTProvider,
    StreamingSTTInvalidResultError,
    StreamingSTTProvider,
    StreamingSTTResult,
    StreamingSTTUnavailableError,
    STTFinal,
    STTPartial,
    UnavailableStreamingSTTProvider,
    validate_streaming_results,
)

__all__ = [
    "BatchSTTError",
    "BatchSTTInvalidResultError",
    "BatchSTTProvider",
    "BatchSTTRequest",
    "BatchSTTSegment",
    "BatchSTTTimeoutError",
    "BatchSTTUnavailableError",
    "DeterministicBatchSTTProvider",
    "DeterministicStreamingSTTProvider",
    "STTFinal",
    "STTPartial",
    "StreamingSTTProvider",
    "StreamingSTTResult",
    "StreamingSTTInvalidResultError",
    "StreamingSTTUnavailableError",
    "UnavailableStreamingSTTProvider",
    "UnavailableBatchSTTProvider",
    "validate_batch_segments",
    "validate_streaming_results",
]
