"""Public, author-anonymous Question API projections."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QuestionCreateRequest(BaseModel):
    """Keep raw input so the service can normalize before measuring length."""

    model_config = ConfigDict(extra="forbid")

    content: str


class QuestionDraftRequest(BaseModel):
    """Raw draft text; service-owned normalization defines its public boundary."""

    model_config = ConfigDict(extra="forbid")

    draft: str


class QuestionDraftResponse(BaseModel):
    """Ephemeral AI suggestions that have not become public Questions."""

    suggestions: list[str]


class QuestionResponse(BaseModel):
    """A member-visible Question; author fields intentionally do not exist here."""

    id: UUID
    session_id: UUID
    content: str
    status: str
    version: int
    clustering_sequence: int
    reaction_count: int
    reacted_by_me: bool
    cluster_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class QuestionClusteringJobRef(BaseModel):
    id: UUID
    attempt: int
    status: str
    mode: str


class QuestionClusteringStateResponse(BaseModel):
    pending: bool
    requested_through_sequence: int
    applied_through_sequence: int
    current_revision: int
    current_generation: int | None
    final_generation: int | None
    active_job_id: UUID | None
    retry_job_id: UUID | None
    last_job: QuestionClusteringJobRef | None


class QuestionCreateResponse(BaseModel):
    question: QuestionResponse
    clustering_state: QuestionClusteringStateResponse


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    next_cursor: str | None


class QuestionReactionState(BaseModel):
    question_id: UUID
    reaction_count: int
    reacted_by_me: bool
