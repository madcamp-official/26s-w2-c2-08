"""Public, safe projections for asynchronous AI Job state."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility
from tbd.models.questions import AIJob

ResourceType = Literal[
    "MATERIAL",
    "QUESTION",
    "QUESTION_CLUSTER_GENERATION",
    "SUMMARY",
    "CHAT_MESSAGE",
    "SESSION",
    "RECORDING",
    "TRANSCRIPT_VERSION",
    "ANSWER",
]

SharedAIJobType = Literal[
    "MATERIAL_PROCESSING",
    "QUESTION_CLUSTERING",
    "FINAL_SUMMARY",
    "SESSION_POSTPROCESSING",
    "RECORDING_TRANSCRIPTION",
    "ANSWER_ORGANIZATION",
    "KNOWLEDGE_INDEXING",
]


class AIJobResourceLink(BaseModel):
    """A stable public link without a provider or internal storage identifier."""

    model_config = ConfigDict(extra="forbid")

    resource_type: ResourceType
    resource_id: str | None
    resource_url: str | None


class AIJobProgress(BaseModel):
    """A user-safe phase name and optional completion estimate."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    percent: int | None = Field(default=None, ge=0, le=100)


class AIJobError(BaseModel):
    """A safe terminal error that never includes provider-originated text."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool


class QuestionClusteringJobContext(BaseModel):
    """The immutable input watermark supplied to a clustering attempt."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["LIVE_INCREMENTAL", "FINAL"]
    input_through_sequence: int = Field(ge=0)
    base_revision: int = Field(ge=0)
    final_answered_through_at: datetime | None


class AIJobResponse(BaseModel):
    """The polling representation shared by every asynchronous API feature."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    job_type: AIJobType
    visibility: AIJobVisibility
    status: AIJobStatus
    attempt: int = Field(ge=1)
    version: int = Field(ge=1)
    progress: AIJobProgress | None
    retryable: bool
    blocks_session_completion: bool
    clustering: QuestionClusteringJobContext | None
    error: AIJobError | None
    target: AIJobResourceLink
    result: AIJobResourceLink | None
    result_unavailable_reason: Literal["SUPERSEDED"] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AIJobAcceptedResponse(BaseModel):
    """The standard asynchronous mutation acknowledgement."""

    model_config = ConfigDict(extra="forbid")

    job: AIJobResponse


class AIJobListResponse(BaseModel):
    """A stable cursor page of Course-visible shared Job rows."""

    model_config = ConfigDict(extra="forbid")

    items: list[AIJobResponse]
    next_cursor: str | None


def project_ai_job(
    job: AIJob,
    *,
    result: AIJobResourceLink | None = None,
    result_unavailable_reason: Literal["SUPERSEDED"] | None = None,
) -> AIJobResponse:
    """Project one Job without exposing run tokens, leases, or internal inputs."""

    progress = (
        AIJobProgress(stage=job.progress_stage, percent=job.progress_percent)
        if job.progress_stage is not None
        else None
    )
    error = (
        AIJobError(
            code=job.error_code,
            message=job.error_message or "작업이 종료되었습니다.",
            retryable=job.retryable,
        )
        if job.error_code is not None
        else None
    )
    clustering = None
    if job.job_type == AIJobType.QUESTION_CLUSTERING:
        assert job.clustering_mode is not None
        assert job.input_through_sequence is not None
        assert job.base_revision is not None
        clustering = QuestionClusteringJobContext(
            mode=job.clustering_mode,
            input_through_sequence=job.input_through_sequence,
            base_revision=job.base_revision,
            final_answered_through_at=job.final_answered_through_at,
        )

    return AIJobResponse(
        id=job.id,
        session_id=job.session_id,
        job_type=job.job_type,
        visibility=job.visibility,
        status=job.status,
        attempt=job.attempt,
        version=job.version,
        progress=progress,
        retryable=job.retryable,
        blocks_session_completion=job.blocks_session_completion,
        clustering=clustering,
        error=error,
        target=_target_link(job),
        result=result,
        result_unavailable_reason=result_unavailable_reason,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _target_link(job: AIJob) -> AIJobResourceLink:
    """Map typed target columns to stable external routes."""

    if job.target_material_id is not None:
        return AIJobResourceLink(
            resource_type="MATERIAL",
            resource_id=str(job.target_material_id),
            resource_url=f"/api/v1/materials/{job.target_material_id}",
        )
    if job.target_recording_id is not None:
        return AIJobResourceLink(
            resource_type="RECORDING",
            resource_id=str(job.target_recording_id),
            resource_url=f"/api/v1/recordings/{job.target_recording_id}/playback",
        )
    if job.target_user_message_id is not None:
        return AIJobResourceLink(
            resource_type="CHAT_MESSAGE",
            resource_id=str(job.target_user_message_id),
            resource_url=f"/api/v1/chat-messages/{job.target_user_message_id}",
        )
    if job.target_answer_id is not None:
        return AIJobResourceLink(
            resource_type="ANSWER",
            resource_id=str(job.target_answer_id),
            resource_url=f"/api/v1/answers/{job.target_answer_id}",
        )
    return AIJobResourceLink(
        resource_type="SESSION",
        resource_id=str(job.session_id),
        resource_url=f"/api/v1/sessions/{job.session_id}",
    )
