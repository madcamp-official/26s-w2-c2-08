"""Validated text controls for the otherwise binary audio WebSocket."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AudioFormatRequest(BaseModel):
    """The only browser-to-server PCM format accepted in MVP v1."""

    model_config = ConfigDict(extra="forbid")

    encoding: Literal["PCM_S16LE"]
    sample_rate_hz: Literal[16000]
    channels: Literal[1]


class AudioStartData(BaseModel):
    """Publisher claim and resume information without a browser access token."""

    model_config = ConfigDict(extra="forbid")

    client_stream_id: str = Field(min_length=1, max_length=256)
    format: AudioFormatRequest
    chunk_duration_ms: Literal[500]
    resume_from_sequence: int | None = Field(default=None, ge=0)

    @field_validator("client_stream_id")
    @classmethod
    def normalize_client_stream_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("client_stream_id must not be blank")
        return normalized


class AudioStartControl(BaseModel):
    """First text control required before any binary frame is accepted."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["audio.start"]
    request_id: str = Field(min_length=1, max_length=128)
    data: AudioStartData


class AudioStopControl(BaseModel):
    """Best-effort control that never delays the HTTP Session end transition."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["audio.stop"]
    request_id: str = Field(min_length=1, max_length=128)
