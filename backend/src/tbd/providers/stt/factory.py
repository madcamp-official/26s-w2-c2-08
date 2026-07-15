"""Settings-backed STT provider construction for API and standalone Workers."""

from dataclasses import dataclass

from tbd.core.config import Settings, STTProviderRuntime
from tbd.providers.stt.batch import BatchSTTProvider, UnavailableBatchSTTProvider
from tbd.providers.stt.streaming import StreamingSTTProvider, UnavailableStreamingSTTProvider


@dataclass(frozen=True, slots=True)
class STTProviders:
    """The Batch and live providers selected from one runtime profile."""

    batch: BatchSTTProvider
    streaming: StreamingSTTProvider


def create_stt_providers(settings: Settings) -> STTProviders:
    """Return safe unavailable providers until local Faster-Whisper is selected."""

    if settings.stt_provider is STTProviderRuntime.UNAVAILABLE:
        return STTProviders(
            batch=UnavailableBatchSTTProvider(),
            streaming=UnavailableStreamingSTTProvider(),
        )

    from tbd.providers.stt.faster_whisper import (
        FasterWhisperBatchSTTProvider,
        FasterWhisperStreamingSTTProvider,
    )

    return STTProviders(
        batch=FasterWhisperBatchSTTProvider(
            model_name=settings.stt_hq_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute_type,
            language=settings.stt_language,
        ),
        streaming=FasterWhisperStreamingSTTProvider(
            model_name=settings.stt_live_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute_type,
            language=settings.stt_language,
            window_ms=settings.stt_live_window_ms,
            finalize_ms=settings.stt_live_finalize_ms,
        ),
    )
