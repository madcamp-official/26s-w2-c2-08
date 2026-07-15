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
from tbd.providers.stt.factory import STTProviders, create_stt_providers
from tbd.providers.stt.faster_whisper import (
    FasterWhisperBatchSTTProvider,
    FasterWhisperStreamingSTTProvider,
)
from tbd.providers.stt.streaming import (
    DeterministicStreamingSTTProvider,
    StreamingSTTInvalidResultError,
    StreamingSTTProvider,
    StreamingSTTRequest,
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
    "FasterWhisperBatchSTTProvider",
    "FasterWhisperStreamingSTTProvider",
    "STTFinal",
    "STTPartial",
    "STTProviders",
    "StreamingSTTRequest",
    "StreamingSTTProvider",
    "StreamingSTTResult",
    "StreamingSTTInvalidResultError",
    "StreamingSTTUnavailableError",
    "UnavailableStreamingSTTProvider",
    "UnavailableBatchSTTProvider",
    "create_stt_providers",
    "validate_batch_segments",
    "validate_streaming_results",
]
