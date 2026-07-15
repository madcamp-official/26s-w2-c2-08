"""Project durable AI Job result ledgers into public resource links."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.clustering import AnswerOrganization, QuestionCluster
from tbd.models.enums import AIJobStatus, AIJobType
from tbd.models.knowledge import ChatMessage, LectureSummary
from tbd.models.materials import TranscriptVersion
from tbd.models.questions import AIJob, QuestionClusteringState
from tbd.schemas.jobs import AIJobResourceLink


@dataclass(frozen=True, slots=True)
class AIJobResultProjection:
    """One public result link or its contract-defined unavailable reason."""

    result: AIJobResourceLink | None = None
    unavailable_reason: Literal["SUPERSEDED"] | None = None


class JobResultIntegrityError(RuntimeError):
    """A successful Job points to no internally consistent result ledger."""


class AIJobResultService:
    """Resolve successful Job output from the authoritative persisted ledger."""

    async def project(self, session: AsyncSession, job: AIJob) -> AIJobResultProjection:
        if job.status != AIJobStatus.SUCCEEDED:
            return AIJobResultProjection()

        if job.job_type in {AIJobType.LIVE_SUMMARY, AIJobType.FINAL_SUMMARY}:
            summary = await session.scalar(
                select(LectureSummary).where(
                    LectureSummary.created_by_job_id == job.id,
                    LectureSummary.created_by_job_attempt == job.attempt,
                )
            )
            if summary is not None:
                return AIJobResultProjection(
                    result=AIJobResourceLink(
                        resource_type="SUMMARY",
                        resource_id=str(summary.id),
                        resource_url=f"/api/v1/summaries/{summary.id}",
                    )
                )
            raise JobResultIntegrityError("summary result is missing")

        if job.job_type == AIJobType.CHAT_RESPONSE:
            message = await session.scalar(
                select(ChatMessage).where(
                    ChatMessage.created_by_job_id == job.id,
                    ChatMessage.created_by_job_attempt == job.attempt,
                )
            )
            if message is not None:
                return AIJobResultProjection(
                    result=AIJobResourceLink(
                        resource_type="CHAT_MESSAGE",
                        resource_id=str(message.id),
                        resource_url=f"/api/v1/chat-messages/{message.id}",
                    )
                )
            raise JobResultIntegrityError("chat response result is missing")

        if job.job_type == AIJobType.RECORDING_TRANSCRIPTION:
            version = await session.scalar(
                select(TranscriptVersion).where(
                    TranscriptVersion.created_by_job_id == job.id,
                    TranscriptVersion.created_by_job_attempt == job.attempt,
                )
            )
            if version is not None:
                return AIJobResultProjection(
                    result=AIJobResourceLink(
                        resource_type="TRANSCRIPT_VERSION",
                        resource_id=str(version.id),
                        resource_url=(
                            f"/api/v1/sessions/{job.session_id}/transcript"
                            f"?transcript_version_id={version.id}"
                        ),
                    )
                )
            raise JobResultIntegrityError("transcript version result is missing")

        if job.job_type == AIJobType.ANSWER_ORGANIZATION:
            organization = await session.scalar(
                select(AnswerOrganization).where(
                    AnswerOrganization.created_by_job_id == job.id,
                    AnswerOrganization.created_by_job_attempt == job.attempt,
                )
            )
            if organization is not None:
                return AIJobResultProjection(
                    result=AIJobResourceLink(
                        resource_type="ANSWER",
                        resource_id=str(organization.answer_id),
                        resource_url=f"/api/v1/answers/{organization.answer_id}",
                    )
                )
            raise JobResultIntegrityError("answer organization result is missing")

        if job.job_type == AIJobType.QUESTION_CLUSTERING:
            state = await session.get(QuestionClusteringState, job.session_id)
            if state is None:
                raise JobResultIntegrityError("clustering state is missing")
            scope = "CURRENT"
            if job.clustering_mode == "FINAL":
                generation = state.final_generation
                scope = "FINAL"
            else:
                generation = state.current_generation
            if generation is None:
                raise JobResultIntegrityError("clustering generation is missing")
            current_result = await session.scalar(
                select(QuestionCluster)
                .where(
                    QuestionCluster.session_id == job.session_id,
                    QuestionCluster.generation == generation,
                )
                .order_by(QuestionCluster.ordinal)
            )
            if current_result is None:
                raise JobResultIntegrityError("clustering generation rows are missing")
            if (
                current_result.created_by_job_id != job.id
                or current_result.created_by_job_attempt != job.attempt
            ):
                return AIJobResultProjection(unavailable_reason="SUPERSEDED")
            return AIJobResultProjection(
                result=AIJobResourceLink(
                    resource_type="QUESTION_CLUSTER_GENERATION",
                    resource_id=str(generation),
                    resource_url=(
                        f"/api/v1/sessions/{job.session_id}/question-clusters?scope={scope}"
                    ),
                )
            )

        return AIJobResultProjection()
