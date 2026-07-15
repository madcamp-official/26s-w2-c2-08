"""Fast contract checks for audio framing and fake Streaming STT behavior."""

import asyncio
from uuid import uuid4

import pytest

from tbd.providers.stt import (
    DeterministicStreamingSTTProvider,
    StreamingSTTRequest,
    STTFinal,
)
from tbd.realtime.audio import (
    FRAME_HEADER,
    PCM_CHUNK_BYTES,
    AudioFrameError,
    parse_audio_frame,
)

pytestmark = pytest.mark.unit


def _frame(*, sequence: int = 0, offset_ms: int = 0, payload: bytes | None = None) -> bytes:
    return FRAME_HEADER.pack(1, 0, sequence, offset_ms) + (payload or (b"\x00" * PCM_CHUNK_BYTES))


def test_pcm_frame_requires_the_fixed_v1_header_and_duration() -> None:
    frame = parse_audio_frame(_frame(sequence=3, offset_ms=1_500))

    assert frame.sequence == 3
    assert frame.captured_offset_ms == 1_500
    assert len(frame.pcm_s16le) == PCM_CHUNK_BYTES

    with pytest.raises(AudioFrameError, match="UNSUPPORTED_AUDIO_FORMAT"):
        parse_audio_frame(FRAME_HEADER.pack(2, 0, 0, 0) + (b"\x00" * PCM_CHUNK_BYTES))
    with pytest.raises(AudioFrameError, match="UNSUPPORTED_AUDIO_FORMAT"):
        parse_audio_frame(FRAME_HEADER.pack(1, 1, 0, 0) + (b"\x00" * PCM_CHUNK_BYTES))
    with pytest.raises(AudioFrameError, match="UNSUPPORTED_AUDIO_FORMAT"):
        parse_audio_frame(FRAME_HEADER.pack(1, 0, 0, 0) + b"\x00")


def test_deterministic_streaming_stt_never_requires_a_network_provider() -> None:
    final = STTFinal(
        utterance_id="utt-1",
        audio_sequence_start=0,
        audio_sequence_end=0,
        start_ms=0,
        end_ms=500,
        text="테스트 문장",
    )
    provider = DeterministicStreamingSTTProvider({0: [final]})

    results = asyncio.run(
        provider.transcribe(
            StreamingSTTRequest(
                session_id=uuid4(),
                recording_id=uuid4(),
                frame=parse_audio_frame(_frame()),
            )
        )
    )

    assert results == (final,)
    assert provider.frames == [0]
