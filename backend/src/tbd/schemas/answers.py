"""Public Answer request and projection schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudentQuestionAnswerTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["STUDENT_QUESTION"]
    question_id: UUID


class RepresentativeQuestionAnswerTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["AI_REPRESENTATIVE_QUESTION"]
    representative_question_id: UUID


AnswerTarget = StudentQuestionAnswerTarget | RepresentativeQuestionAnswerTarget


class AnswerCreateRequest(BaseModel):
    """One typed target; VOICE and TEXT are constrained by the service state machine."""

    model_config = ConfigDict(extra="forbid")

    answer_type: Literal["VOICE", "TEXT"]
    target: AnswerTarget
    text_content: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "AnswerCreateRequest":
        if self.answer_type == "VOICE" and self.text_content is not None:
            raise ValueError("VOICE Answer must not include text_content")
        if self.answer_type == "TEXT" and (
            not isinstance(self.target, StudentQuestionAnswerTarget) or self.text_content is None
        ):
            raise ValueError("TEXT Answer requires a student Question and text_content")
        return self


class AnswerCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript_version_id: UUID
    start_sequence: int = Field(ge=1)
    end_sequence: int = Field(ge=1)


class AnswerTextUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_content: str
    expected_version: int = Field(ge=1)


class AnswerTranscriptMappingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_transcript_version_id: UUID
    status: Literal["PENDING", "SUCCEEDED", "FAILED"]
    start_segment_id: UUID | None
    end_segment_id: UUID | None
    updated_at: datetime


class AnswerOrganizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    source_transcript_version_id: UUID
    start_sequence: int = Field(ge=1)
    end_sequence: int = Field(ge=1)
    created_by_job_id: UUID
    created_by_job_attempt: int = Field(ge=1)
    model_name: str | None
    prompt_version: str | None
    created_at: datetime


class AnswerOrganizationStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "NOT_APPLICABLE",
        "NOT_STARTED",
        "WAITING_SOURCE",
        "PENDING",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "DATA_INTEGRITY_ERROR",
    ]
    job_id: UUID | None = None
    attempt: int | None = None
    retryable: bool = False
    organization: AnswerOrganizationResponse | None = None


class AnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    answer_type: Literal["VOICE", "TEXT"]
    status: Literal["CAPTURING", "COMPLETED"]
    version: int
    target: AnswerTarget
    target_text_snapshot: str
    text_content: str | None
    source_transcript_version_id: UUID | None
    canonical_transcript_mapping: AnswerTranscriptMappingResponse | None
    organization_state: AnswerOrganizationStateResponse
    capture_started_after_sequence: int | None
    start_sequence: int | None
    end_sequence: int | None
    started_at: datetime
    completed_at: datetime | None
    updated_at: datetime


class AnswerListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnswerResponse]
    next_cursor: str | None
