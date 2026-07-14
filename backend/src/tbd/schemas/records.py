"""Compact, authorization-safe projections for completed class records."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tbd.schemas.clustering import QuestionClusteringStateResponse
from tbd.schemas.recordings import SessionRecordingResponse
from tbd.schemas.sessions import LectureSessionResponse
from tbd.schemas.transcripts import TranscriptAggregateResponse


class RecordCollectionIndex(BaseModel):
    """A bounded collection summary and its cursor-free first-page URL."""

    model_config = ConfigDict(extra="forbid")

    total_count: int = Field(ge=0)
    list_url: str


class RecordTranscriptIndex(BaseModel):
    """The selected durable transcript scope without embedding timeline rows."""

    model_config = ConfigDict(extra="forbid")

    state: TranscriptAggregateResponse | None
    selected_version_id: UUID | None
    segment_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    timeline_url: str
    versions_url: str


class FinalSummaryReason(BaseModel):
    """A small, user-safe explanation for terminal FINAL Summary source states."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["NO_FINAL_TRANSCRIPT", "SUMMARY_SOURCE_UNAVAILABLE"]
    message: str


class FinalSummaryState(BaseModel):
    """The persisted FINAL Summary state, never an inferred provider error."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["PENDING", "AVAILABLE", "FAILED", "NOT_APPLICABLE", "DATA_INTEGRITY_ERROR"]
    reason: FinalSummaryReason | None

    @model_validator(mode="after")
    def validate_reason(self) -> "FinalSummaryState":
        if self.status == "NOT_APPLICABLE":
            if self.reason is None or self.reason.code != "NO_FINAL_TRANSCRIPT":
                raise ValueError("NOT_APPLICABLE requires NO_FINAL_TRANSCRIPT")
        elif self.status == "FAILED":
            if self.reason is not None and self.reason.code != "SUMMARY_SOURCE_UNAVAILABLE":
                raise ValueError("FAILED only permits SUMMARY_SOURCE_UNAVAILABLE")
        elif self.reason is not None:
            raise ValueError("this FINAL Summary state cannot include a reason")
        return self


class RecordSummaryIndex(BaseModel):
    """A FINAL Summary status plus stable singleton and collection URLs."""

    model_config = ConfigDict(extra="forbid")

    state: FinalSummaryState
    summary_url: str | None
    summaries_url: str


class RecordQuestionClustersIndex(BaseModel):
    """Current and FINAL cluster collections remain independently pageable."""

    model_config = ConfigDict(extra="forbid")

    state: QuestionClusteringStateResponse
    current: RecordCollectionIndex
    final: RecordCollectionIndex


class SessionRecordResponse(BaseModel):
    """The small record manifest used to initialize an ended-class page."""

    model_config = ConfigDict(extra="forbid")

    session: LectureSessionResponse
    recording: SessionRecordingResponse | None
    recording_url: str
    materials: RecordCollectionIndex
    transcript: RecordTranscriptIndex
    summary: RecordSummaryIndex
    questions: RecordCollectionIndex
    question_clusters: RecordQuestionClustersIndex
    answers: RecordCollectionIndex
    jobs: RecordCollectionIndex
