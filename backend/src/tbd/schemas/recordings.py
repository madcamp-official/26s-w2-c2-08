"""Public request and response contracts for recording upload and playback."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tbd.schemas.jobs import AIJobResponse
from tbd.schemas.transcripts import TranscriptVersionResponse
from tbd.storage import validate_sha256

RecordingStatusValue = Literal[
    "CAPTURING",
    "UPLOAD_PENDING",
    "UPLOADING",
    "UPLOADED",
    "FAILED",
]
RecordingUploadStatusValue = Literal["ACTIVE", "COMPLETED", "EXPIRED", "FAILED"]
RecordingContentType = Literal["audio/webm", "audio/mp4"]


class RecordingUploadCreateRequest(BaseModel):
    """Declare one resumable browser recording upload before sending bytes."""

    model_config = ConfigDict(extra="forbid")

    client_stream_id: str = Field(min_length=1, max_length=256)
    content_type: str = Field(
        min_length=1,
        max_length=128,
        json_schema_extra={"enum": ["audio/webm", "audio/mp4"]},
    )
    total_bytes: int = Field(ge=1, json_schema_extra={"maximum": 100_000_000})
    duration_ms: int = Field(ge=0)

    @field_validator("client_stream_id")
    @classmethod
    def normalize_client_stream_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("client_stream_id must not be blank")
        return normalized

    @field_validator("content_type")
    @classmethod
    def normalize_content_type(cls, value: str) -> str:
        return value.split(";", 1)[0].strip().lower()


class RecordingUploadCompleteRequest(BaseModel):
    """Bind a completed upload to the client-observed whole-object checksum."""

    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(json_schema_extra={"pattern": "^[0-9a-f]{64}$"})

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        try:
            return validate_sha256(value)
        except ValueError as exc:
            raise ValueError("sha256 must be a 64-character hexadecimal digest") from exc


class SessionRecordingResponse(BaseModel):
    """A Course-member safe recording projection without private storage data."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    session_id: UUID
    status: RecordingStatusValue
    content_type: RecordingContentType | None
    byte_size: int | None = Field(ge=1)
    duration_ms: int | None = Field(ge=0)
    version: int = Field(ge=1)
    playback_url: str | None
    created_at: datetime
    updated_at: datetime


class RecordingUploadResponse(BaseModel):
    """The private-to-publisher resumable upload state."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    recording_id: UUID
    status: RecordingUploadStatusValue
    offset_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=1)
    expires_at: datetime
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class RecordingUploadCompleteResponse(BaseModel):
    """The durable recording, staged transcript revision, and queued HQ STT work."""

    model_config = ConfigDict(extra="forbid")

    recording: SessionRecordingResponse
    transcript_version: TranscriptVersionResponse
    job: AIJobResponse
