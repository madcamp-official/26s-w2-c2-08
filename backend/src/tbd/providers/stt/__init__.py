"""Streaming STT abstractions owned by the live audio boundary."""

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
    "DeterministicStreamingSTTProvider",
    "STTFinal",
    "STTPartial",
    "StreamingSTTProvider",
    "StreamingSTTResult",
    "StreamingSTTInvalidResultError",
    "StreamingSTTUnavailableError",
    "UnavailableStreamingSTTProvider",
    "validate_streaming_results",
]
