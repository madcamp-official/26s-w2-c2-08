"""Public projections for LIVE Question cluster generations."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from tbd.schemas.questions import QuestionClusteringStateResponse, QuestionResponse


class RepresentativeQuestionResponse(BaseModel):
    """Immutable public AI wording; internal discarded rows are never returned."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    content: str
    lifecycle_status: Literal["ACTIVE", "PRESERVED"]
    status: Literal["OPEN", "SELECTED", "ANSWERED"]
    version: int
    answer_id: UUID | None
    created_by_job_id: UUID
    created_by_job_attempt: int
    created_in_generation: int
    created_at: datetime


class QuestionClusterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    generation: int
    revision: int
    ordinal: int
    representative_question: RepresentativeQuestionResponse
    member_count: int
    members_url: str
    is_final: bool
    finalized_at: datetime | None
    created_by_job_id: UUID
    created_by_job_attempt: int


class QuestionClusterListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["CURRENT", "FINAL"]
    clustering_state: QuestionClusteringStateResponse
    generation: int | None
    items: list[QuestionClusterResponse]
    next_cursor: str | None


class StudentQuestionClusterMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["STUDENT_QUESTION"]
    ordinal: int
    question: QuestionResponse


class RepresentativeQuestionClusterMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["AI_REPRESENTATIVE"]
    ordinal: int
    representative_question: RepresentativeQuestionResponse


QuestionClusterMemberResponse = StudentQuestionClusterMember | RepresentativeQuestionClusterMember


class QuestionClusterMemberListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: UUID
    items: list[QuestionClusterMemberResponse]
    next_cursor: str | None
