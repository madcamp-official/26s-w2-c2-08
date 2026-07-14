"""Public projections for requester-only Summary and Chat resources."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tbd.schemas.jobs import AIJobResponse


class SummaryRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sequence: int | None = Field(ge=1)
    end_sequence: int | None = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if (
            self.start_sequence is not None
            and self.end_sequence is not None
            and self.start_sequence > self.end_sequence
        ):
            raise ValueError("start_sequence must not exceed end_sequence")
        return self


class SummaryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_type: Literal["LIVE"]
    range: SummaryRange | None


class LectureSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    job_id: UUID
    summary_type: Literal["LIVE", "FINAL"]
    visibility: Literal["REQUESTER_ONLY", "COURSE_MEMBERS"]
    content: str
    source_transcript_version_id: UUID
    source_start_sequence: int
    source_end_sequence: int
    model_name: str | None
    prompt_version: str | None
    created_at: datetime


class SummaryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_status: Literal[
        "NOT_STARTED", "PENDING", "AVAILABLE", "FAILED", "NOT_APPLICABLE", "DATA_INTEGRITY_ERROR"
    ]
    summary_reason: dict[str, str] | None
    items: list[LectureSummaryResponse]
    next_cursor: str | None


class ChatCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["LIVE", "REVIEW"]


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    mode: Literal["LIVE", "REVIEW"]
    created_at: datetime
    updated_at: datetime


class ChatListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChatResponse]
    next_cursor: str | None


class ChatMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class ChatEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["MATERIAL", "TRANSCRIPT", "QUESTION", "ANSWER"]
    label: str
    link: str | None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    chat_id: UUID
    job_id: UUID | None
    response_job_id: UUID | None
    sequence: int
    role: Literal["USER", "ASSISTANT"]
    content: str
    evidence: list[ChatEvidenceResponse]
    model_name: str | None
    prompt_version: str | None
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChatMessageResponse]
    next_cursor: str | None


class ChatTurnAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: ChatMessageResponse
    job: AIJobResponse
