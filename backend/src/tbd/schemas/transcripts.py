"""Safe REST projections for durable final transcript state only."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TranscriptVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    source: Literal["LIVE", "RECORDING"]
    status: Literal["FINALIZING", "FINALIZED", "FAILED", "EMPTY"]
    version: int = Field(ge=1)
    last_sequence: int = Field(ge=0)
    is_canonical: bool
    recording_id: UUID | None
    created_by_job_id: UUID | None
    created_by_job_attempt: int | None = Field(default=None, ge=1)
    finalized_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    transcript_version_id: UUID
    item_type: Literal["SEGMENT"] = "SEGMENT"
    sequence: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    recording_start_ms: int | None = Field(default=None, ge=0)
    recording_end_ms: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1)
    created_at: datetime


class TranscriptGapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    transcript_version_id: UUID
    item_type: Literal["GAP"] = "GAP"
    start_ms: int = Field(ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    is_final: bool
    reason: Literal["SERVER_STATE_LOST", "SEQUENCE_GAP", "CLIENT_DISCONNECTED", "BACKPRESSURE_DROP"]
    created_at: datetime


class TranscriptAggregateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    status: Literal["FINALIZING", "FINALIZED", "FAILED", "EMPTY"]
    current_version: TranscriptVersionResponse
    canonical_version_id: UUID | None
    canonical_version: TranscriptVersionResponse | None
    updated_at: datetime


class TranscriptTimelinePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: TranscriptAggregateResponse
    selected_version: TranscriptVersionResponse
    segments: list[TranscriptSegmentResponse]
    gaps: list[TranscriptGapResponse]
    next_cursor: str | None


class TranscriptVersionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TranscriptVersionResponse]
    next_cursor: str | None
