"""Provider-neutral live STT results with deterministic test behavior."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from tbd.realtime.audio import AudioFrame


class StreamingSTTUnavailableError(Exception):
    """The configured live provider cannot currently accept audio."""


class StreamingSTTInvalidResultError(Exception):
    """A provider returned data that cannot safely enter the realtime boundary."""


@dataclass(frozen=True)
class STTPartial:
    utterance_id: str
    revision: int
    audio_sequence_start: int
    audio_sequence_end: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class STTFinal:
    utterance_id: str
    audio_sequence_start: int
    audio_sequence_end: int
    start_ms: int
    end_ms: int
    text: str


type StreamingSTTResult = STTPartial | STTFinal


@dataclass(frozen=True)
class StreamingSTTRequest:
    """One live PCM frame with the durable scope required for provider state."""

    session_id: UUID
    recording_id: UUID
    frame: AudioFrame


def validate_streaming_results(
    results: Sequence[StreamingSTTResult],
) -> tuple[StreamingSTTResult, ...]:
    """Reject malformed provider output before it can become an event or a DB row."""

    validated: list[StreamingSTTResult] = []
    for result in results:
        if not isinstance(result, (STTPartial, STTFinal)):
            raise StreamingSTTInvalidResultError
        if (
            not result.utterance_id.strip()
            or not result.text.strip()
            or result.audio_sequence_start > result.audio_sequence_end
            or result.start_ms < 0
            or result.end_ms < result.start_ms
        ):
            raise StreamingSTTInvalidResultError
        if isinstance(result, STTPartial) and result.revision < 1:
            raise StreamingSTTInvalidResultError
        validated.append(result)
    return tuple(validated)


class StreamingSTTProvider(Protocol):
    """Translate one scoped PCM frame without exposing a provider SDK upstream."""

    async def transcribe(self, request: StreamingSTTRequest) -> Sequence[StreamingSTTResult]: ...


class UnavailableStreamingSTTProvider:
    """Safe default until an external live STT runtime is selected and configured."""

    async def transcribe(self, request: StreamingSTTRequest) -> Sequence[StreamingSTTResult]:
        del request
        raise StreamingSTTUnavailableError


class DeterministicStreamingSTTProvider:
    """Map PCM sequence numbers to fixed results for tests without network access."""

    def __init__(self, results: Mapping[int, Sequence[StreamingSTTResult]] | None = None) -> None:
        self._results = dict(results or {})
        self.frames: list[int] = []

    async def transcribe(self, request: StreamingSTTRequest) -> Sequence[StreamingSTTResult]:
        self.frames.append(request.frame.sequence)
        return tuple(self._results.get(request.frame.sequence, ()))
