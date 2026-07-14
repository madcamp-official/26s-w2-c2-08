"""Batch STT abstractions for post-class recording transcription.

The production provider remains intentionally unselected.  This module keeps
the worker independent from a vendor while the deterministic implementation
makes every terminal path reproducible in local development and CI.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class BatchSTTError(RuntimeError):
    """Base Batch STT failure with a safe worker-facing classification."""

    retryable = False


class BatchSTTUnavailableError(BatchSTTError):
    """The provider is temporarily unavailable and the job may be retried."""

    retryable = True


class BatchSTTTimeoutError(BatchSTTError):
    """The provider could not return before the Session processing deadline."""

    retryable = True


class BatchSTTInvalidResultError(BatchSTTError):
    """The provider returned a result that cannot become durable Transcript data."""


@dataclass(frozen=True, slots=True)
class BatchSTTRequest:
    """Private recording bytes and the Session-scoped deadline for one attempt."""

    content: bytes
    content_type: str
    duration_ms: int
    deadline: datetime


@dataclass(frozen=True, slots=True)
class BatchSTTSegment:
    """One final sentence with both Transcript and Recording time coordinates."""

    start_ms: int
    end_ms: int
    recording_start_ms: int
    recording_end_ms: int
    text: str


class BatchSTTProvider(Protocol):
    """Vendor-neutral post-class transcription contract."""

    async def transcribe(self, request: BatchSTTRequest) -> Sequence[BatchSTTSegment]:
        """Return ordered final segments, or an empty sequence for no speech."""


class DeterministicBatchSTTProvider:
    """A configurable fake provider that performs no network or model call."""

    def __init__(
        self,
        results: Sequence[BatchSTTSegment] = (),
        *,
        error: BatchSTTError | None = None,
    ) -> None:
        self.results = tuple(results)
        self.error = error
        self.requests: list[BatchSTTRequest] = []

    async def transcribe(self, request: BatchSTTRequest) -> Sequence[BatchSTTSegment]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.results


class UnavailableBatchSTTProvider:
    """Safe default for a deployment where no external Batch STT is configured."""

    async def transcribe(self, request: BatchSTTRequest) -> Sequence[BatchSTTSegment]:
        del request
        raise BatchSTTUnavailableError("Batch STT provider is not configured")


def validate_batch_segments(
    results: Sequence[BatchSTTSegment], *, duration_ms: int
) -> tuple[BatchSTTSegment, ...]:
    """Reject malformed or unordered provider data before a DB transaction starts."""

    if duration_ms < 0:
        raise BatchSTTInvalidResultError("recording duration must not be negative")
    normalized: list[BatchSTTSegment] = []
    previous_start = -1
    for result in results:
        text = result.text.strip()
        if not text:
            raise BatchSTTInvalidResultError("Batch STT segment text must not be blank")
        if (
            result.start_ms < 0
            or result.end_ms < result.start_ms
            or result.recording_start_ms < 0
            or result.recording_end_ms < result.recording_start_ms
            or result.end_ms > duration_ms
            or result.recording_end_ms > duration_ms
            or result.start_ms < previous_start
        ):
            raise BatchSTTInvalidResultError("Batch STT segment timestamps are invalid")
        previous_start = result.start_ms
        normalized.append(
            BatchSTTSegment(
                start_ms=result.start_ms,
                end_ms=result.end_ms,
                recording_start_ms=result.recording_start_ms,
                recording_end_ms=result.recording_end_ms,
                text=text,
            )
        )
    return tuple(normalized)
