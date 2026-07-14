"""Public HTTP and WebSocket payloads for Course realtime notifications."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tbd.models.enums import RealtimeTicketScope


class RealtimeTicketCreateRequest(BaseModel):
    """Request a one-time ticket for exactly one realtime channel."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    scope: RealtimeTicketScope
    resume_cursor: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_resume_scope(self) -> "RealtimeTicketCreateRequest":
        if self.scope == RealtimeTicketScope.SESSION_AUDIO_WRITE and self.resume_cursor is not None:
            raise ValueError("resume_cursor is only available for SESSION_EVENTS_READ")
        return self


class RealtimeTicketResponse(BaseModel):
    """The secret is returned only once and must never be persisted by the client."""

    model_config = ConfigDict(extra="forbid")

    ticket: str = Field(min_length=1)
    session_id: UUID
    scope: RealtimeTicketScope
    expires_at: datetime


class RealtimeEvent(BaseModel):
    """Safe server-to-client envelope; REST resources remain canonical."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    event_id: UUID
    type: str
    session_id: UUID
    cursor: str | None
    resource_version: int | None
    correlation_id: str | None
    occurred_at: datetime
    data: dict[str, object]
