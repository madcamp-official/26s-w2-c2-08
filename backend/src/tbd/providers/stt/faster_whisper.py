"""Local Faster-Whisper adapters for final recordings and buffered live PCM."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from tbd.providers.stt.batch import (
    BatchSTTRequest,
    BatchSTTSegment,
    BatchSTTTimeoutError,
    BatchSTTUnavailableError,
)
from tbd.providers.stt.streaming import (
    StreamingSTTRequest,
    StreamingSTTResult,
    StreamingSTTUnavailableError,
    STTFinal,
    STTPartial,
)
from tbd.realtime.audio import PCM_CHUNK_DURATION_MS


def _load_model(model_name: str, *, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise BatchSTTUnavailableError("faster-whisper is not installed") from exc
    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:
        raise BatchSTTUnavailableError("local STT model is unavailable") from exc


@dataclass(slots=True)
class _ModelRuntime:
    model_name: str
    device: str
    compute_type: str
    _model: object | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def transcribe(self, audio: object, *, language: str) -> list[object]:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio, language)

    def _transcribe_sync(self, audio: object, language: str) -> list[object]:
        if self._model is None:
            self._model = _load_model(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        try:
            segments, _ = self._model.transcribe(
                audio,
                language=language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return list(segments)
        except BatchSTTUnavailableError:
            raise
        except Exception as exc:
            raise BatchSTTUnavailableError("local STT inference failed") from exc


class FasterWhisperBatchSTTProvider:
    """Transcribe an uploaded recording through one lazy local GPU model."""

    def __init__(self, *, model_name: str, device: str, compute_type: str, language: str) -> None:
        self.language = language
        self._runtime = _ModelRuntime(model_name, device, compute_type)

    async def transcribe(self, request: BatchSTTRequest) -> tuple[BatchSTTSegment, ...]:
        remaining = (request.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise BatchSTTTimeoutError("recording deadline elapsed")
        suffix = _suffix_for_content_type(request.content_type)
        path = await asyncio.to_thread(_write_temporary_audio, request.content, suffix)
        try:
            try:
                segments = await asyncio.wait_for(
                    self._runtime.transcribe(str(path), language=self.language),
                    timeout=remaining,
                )
            except TimeoutError as exc:
                raise BatchSTTTimeoutError("local STT timed out") from exc
            return tuple(_as_batch_segment(segment, request.duration_ms) for segment in segments)
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)


@dataclass(slots=True)
class _LiveBuffer:
    start_ms: int
    sequence_start: int
    sequence_end: int
    pcm: bytearray = field(default_factory=bytearray)
    revision: int = 0
    last_partial_ms: int = 0


class FasterWhisperStreamingSTTProvider:
    """Buffer scoped 16 kHz PCM and emit partials before bounded final windows."""

    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        compute_type: str,
        language: str,
        window_ms: int,
        finalize_ms: int,
    ) -> None:
        self.language = language
        self.window_ms = window_ms
        self.finalize_ms = finalize_ms
        self._runtime = _ModelRuntime(model_name, device, compute_type)
        self._buffers: dict[UUID, _LiveBuffer] = {}

    async def transcribe(self, request: StreamingSTTRequest) -> tuple[StreamingSTTResult, ...]:
        frame = request.frame
        buffer = self._buffers.get(request.session_id)
        if buffer is None:
            buffer = _LiveBuffer(
                start_ms=frame.captured_offset_ms,
                sequence_start=frame.sequence,
                sequence_end=frame.sequence,
            )
            self._buffers[request.session_id] = buffer
        buffer.sequence_end = frame.sequence
        buffer.pcm.extend(frame.pcm_s16le)
        end_ms = frame.captured_offset_ms + PCM_CHUNK_DURATION_MS
        duration_ms = end_ms - buffer.start_ms
        if duration_ms < self.window_ms or duration_ms - buffer.last_partial_ms < self.window_ms:
            return ()
        text = await self._transcribe_pcm(bytes(buffer.pcm))
        if not text:
            return ()
        utterance_id = f"live-{request.session_id}-{buffer.sequence_start}"
        if duration_ms >= self.finalize_ms:
            self._buffers.pop(request.session_id, None)
            return (
                STTFinal(
                    utterance_id=utterance_id,
                    audio_sequence_start=buffer.sequence_start,
                    audio_sequence_end=buffer.sequence_end,
                    start_ms=buffer.start_ms,
                    end_ms=end_ms,
                    text=text,
                ),
            )
        buffer.revision += 1
        buffer.last_partial_ms = duration_ms
        return (
            STTPartial(
                utterance_id=utterance_id,
                revision=buffer.revision,
                audio_sequence_start=buffer.sequence_start,
                audio_sequence_end=buffer.sequence_end,
                start_ms=buffer.start_ms,
                end_ms=end_ms,
                text=text,
            ),
        )

    async def _transcribe_pcm(self, pcm: bytes) -> str:
        try:
            import numpy
        except ImportError as exc:
            raise StreamingSTTUnavailableError("numpy is not installed") from exc
        samples = numpy.frombuffer(pcm, dtype="<i2").astype("float32") / 32768.0
        try:
            segments = await self._runtime.transcribe(samples, language=self.language)
        except BatchSTTUnavailableError as exc:
            raise StreamingSTTUnavailableError("local STT inference failed") from exc
        return " ".join(
            str(segment.text).strip() for segment in segments if str(segment.text).strip()
        )


def _write_temporary_audio(content: bytes, suffix: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix="goal-stt-", suffix=suffix)
    path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _suffix_for_content_type(content_type: str) -> str:
    if "webm" in content_type:
        return ".webm"
    if "wav" in content_type:
        return ".wav"
    if "mpeg" in content_type or "mp3" in content_type:
        return ".mp3"
    return ".audio"


def _as_batch_segment(segment: object, duration_ms: int) -> BatchSTTSegment:
    start_ms = max(0, min(duration_ms, round(float(segment.start) * 1000)))
    end_ms = max(start_ms, min(duration_ms, round(float(segment.end) * 1000)))
    return BatchSTTSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        recording_start_ms=start_ms,
        recording_end_ms=end_ms,
        text=str(segment.text),
    )
