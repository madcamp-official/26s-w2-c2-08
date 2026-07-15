"""Unit coverage for local Faster-Whisper adapters without a model download."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tbd.core.config import Settings, STTProviderRuntime
from tbd.providers.stt import (
    FasterWhisperBatchSTTProvider,
    FasterWhisperStreamingSTTProvider,
    StreamingSTTRequest,
    STTFinal,
    STTPartial,
    UnavailableBatchSTTProvider,
    UnavailableStreamingSTTProvider,
    create_stt_providers,
)
from tbd.providers.stt.faster_whisper import _as_batch_segment
from tbd.realtime.audio import PCM_CHUNK_BYTES, AudioFrame

pytestmark = pytest.mark.unit


def test_stt_factory_defaults_to_safe_unavailable_providers() -> None:
    """Development and CI never load a GPU model without explicit operator choice."""

    providers = create_stt_providers(Settings(_env_file=None))

    assert isinstance(providers.batch, UnavailableBatchSTTProvider)
    assert isinstance(providers.streaming, UnavailableStreamingSTTProvider)


def test_stt_factory_selects_lazy_faster_whisper_adapters() -> None:
    """Selecting Faster-Whisper constructs adapters but does not load a model yet."""

    providers = create_stt_providers(
        Settings(_env_file=None, stt_provider=STTProviderRuntime.FASTER_WHISPER)
    )

    assert isinstance(providers.batch, FasterWhisperBatchSTTProvider)
    assert isinstance(providers.streaming, FasterWhisperStreamingSTTProvider)


def test_stt_live_window_cannot_exceed_the_final_window() -> None:
    """A final boundary shorter than the partial window cannot make progress."""

    with pytest.raises(ValidationError, match="STT_LIVE_FINALIZE_MS"):
        Settings(_env_file=None, stt_live_window_ms=2000, stt_live_finalize_ms=1000)


def test_live_faster_whisper_provider_emits_partial_then_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One Session buffer must retain its scope and turn a bounded window final."""

    provider = FasterWhisperStreamingSTTProvider(
        model_name="test-model",
        device="cpu",
        compute_type="int8",
        language="ko",
        window_ms=1000,
        finalize_ms=2000,
    )

    async def fake_transcribe(_pcm: bytes) -> str:
        return "확정할 강의 문장"

    monkeypatch.setattr(provider, "_transcribe_pcm", fake_transcribe)
    session_id = uuid4()
    recording_id = uuid4()

    def request(sequence: int) -> StreamingSTTRequest:
        return StreamingSTTRequest(
            session_id=session_id,
            recording_id=recording_id,
            frame=AudioFrame(
                sequence=sequence,
                captured_offset_ms=sequence * 500,
                pcm_s16le=b"\x00" * PCM_CHUNK_BYTES,
            ),
        )

    assert asyncio.run(provider.transcribe(request(0))) == ()
    partial = asyncio.run(provider.transcribe(request(1)))
    assert isinstance(partial[0], STTPartial)
    assert partial[0].revision == 1
    assert asyncio.run(provider.transcribe(request(2))) == ()
    final = asyncio.run(provider.transcribe(request(3)))
    assert isinstance(final[0], STTFinal)
    assert final[0].audio_sequence_start == 0
    assert final[0].audio_sequence_end == 3


def test_batch_segment_preserves_recording_seek_coordinates() -> None:
    """A Faster-Whisper time range maps to both Transcript and recording timelines."""

    segment = _as_batch_segment(
        SimpleNamespace(start=0.125, end=1.5, text="  녹음 기반 문장  "),
        duration_ms=2000,
    )

    assert (segment.start_ms, segment.end_ms) == (125, 1500)
    assert (segment.recording_start_ms, segment.recording_end_ms) == (125, 1500)
    assert segment.text == "  녹음 기반 문장  "
