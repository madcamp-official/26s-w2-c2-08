"""Provider-neutral live STT results with deterministic test behavior."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from tbd.realtime.audio import AudioFrame


class StreamingSTTUnavailableError(Exception):
    """The configured live provider cannot currently accept audio."""


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


class StreamingSTTProvider(Protocol):
    """Translate one fixed PCM frame without exposing a provider SDK upstream."""

    async def transcribe(self, frame: AudioFrame) -> Sequence[StreamingSTTResult]: ...


class UnavailableStreamingSTTProvider:
    """Safe default until an external live STT runtime is selected and configured."""

    async def transcribe(self, frame: AudioFrame) -> Sequence[StreamingSTTResult]:
        del frame
        raise StreamingSTTUnavailableError


class DeterministicStreamingSTTProvider:
    """Map PCM sequence numbers to fixed results for tests without network access."""

    def __init__(self, results: Mapping[int, Sequence[StreamingSTTResult]] | None = None) -> None:
        self._results = dict(results or {})
        self.frames: list[int] = []

    async def transcribe(self, frame: AudioFrame) -> Sequence[StreamingSTTResult]:
        self.frames.append(frame.sequence)
        return tuple(self._results.get(frame.sequence, ()))
