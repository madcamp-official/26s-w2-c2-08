"""Strict MVP v1 PCM frame parsing for the audio WebSocket."""

from dataclasses import dataclass
from struct import Struct

PROTOCOL_VERSION = 1
PCM_SAMPLE_RATE_HZ = 16_000
PCM_CHANNELS = 1
PCM_CHUNK_DURATION_MS = 500
PCM_CHUNK_BYTES = 16_000
MAX_FRAME_BYTES = 32_768
FRAME_HEADER = Struct("!BBIQ")


class AudioFrameError(ValueError):
    """A client binary frame violates the public audio wire contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AudioFrame:
    """A parsed frame with no retained copy outside the current STT handoff."""

    sequence: int
    captured_offset_ms: int
    pcm_s16le: bytes


def parse_audio_frame(frame: bytes) -> AudioFrame:
    """Validate version, fixed PCM duration, and the bounded binary envelope."""

    if len(frame) > MAX_FRAME_BYTES:
        raise AudioFrameError("AUDIO_CHUNK_TOO_LARGE")
    if len(frame) < FRAME_HEADER.size:
        raise AudioFrameError("INVALID_AUDIO_FRAME")
    protocol_version, flags, sequence, captured_offset_ms = FRAME_HEADER.unpack_from(frame)
    if protocol_version != PROTOCOL_VERSION or flags != 0:
        raise AudioFrameError("UNSUPPORTED_AUDIO_FORMAT")
    pcm_s16le = frame[FRAME_HEADER.size :]
    if len(pcm_s16le) != PCM_CHUNK_BYTES:
        raise AudioFrameError("UNSUPPORTED_AUDIO_FORMAT")
    return AudioFrame(
        sequence=sequence,
        captured_offset_ms=captured_offset_ms,
        pcm_s16le=pcm_s16le,
    )
