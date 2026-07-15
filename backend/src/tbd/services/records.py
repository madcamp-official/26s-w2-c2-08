"""Read-only, compact record manifests for PROCESSING and COMPLETED classes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.clustering import Answer, QuestionCluster
from tbd.models.courses import CourseMember
from tbd.models.materials import (
    LectureMaterial,
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.models.questions import AIJob, Question, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.schemas.records import (
    FinalSummaryReason,
    FinalSummaryState,
    RecordCollectionIndex,
    RecordQuestionClustersIndex,
    RecordSummaryIndex,
    RecordTranscriptIndex,
    SessionRecordResponse,
)
from tbd.schemas.sessions import LectureSessionResponse
from tbd.services.personal_ai import PersonalAIService
from tbd.services.questions import QuestionService
from tbd.services.recordings import recording_response
from tbd.services.transcripts import TranscriptService


class RecordNotFoundError(Exception):
    """The requested Session does not exist."""


class RecordAccessDeniedError(Exception):
    """The caller is not a current Course member."""


class RecordSessionStateError(Exception):
    """Only a PROCESSING or COMPLETED Session has a record manifest."""


@dataclass(frozen=True, slots=True)
class _TranscriptProjection:
    state: object | None
    selected_version_id: UUID | None
    segment_count: int
    gap_count: int


class RecordService:
    """Build bounded record indices from the durable relational source of truth."""

    async def get_for_member(
        self, session: AsyncSession, *, session_id: UUID, user_id: UUID
    ) -> SessionRecordResponse:
        lecture_session = await session.get(LectureSession, session_id)
        if lecture_session is None:
            raise RecordNotFoundError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id,
                CourseMember.user_id == user_id,
            )
        )
        if role is None:
            raise RecordAccessDeniedError
        if lecture_session.status not in {"PROCESSING", "COMPLETED"}:
            raise RecordSessionStateError

        recording = await session.scalar(
            select(SessionRecording).where(SessionRecording.session_id == lecture_session.id)
        )
        transcript = await self._transcript_index(session, lecture_session)
        summary = await self._summary_index(
            session, lecture_session=lecture_session, user_id=user_id
        )
        clustering_state = await self._clustering_state(session, lecture_session)

        material_count = await self._count(
            session,
            select(func.count())
            .select_from(LectureMaterial)
            .where(
                LectureMaterial.session_id == lecture_session.id,
                LectureMaterial.detached_at.is_(None),
            ),
        )
        question_count = await self._count(
            session,
            select(func.count())
            .select_from(Question)
            .where(Question.session_id == lecture_session.id),
        )
        answer_count = await self._count(
            session,
            select(func.count()).select_from(Answer).where(Answer.session_id == lecture_session.id),
        )
        shared_job_count = await self._count(
            session,
            select(func.count())
            .select_from(AIJob)
            .where(AIJob.session_id == lecture_session.id, AIJob.visibility == "SHARED"),
        )

        base = f"/api/v1/sessions/{lecture_session.id}"
        return SessionRecordResponse(
            session=LectureSessionResponse.model_validate(lecture_session),
            recording=recording_response(recording) if recording is not None else None,
            recording_url=f"{base}/recording",
            materials=RecordCollectionIndex(
                total_count=material_count, list_url=f"{base}/materials"
            ),
            transcript=RecordTranscriptIndex(
                state=transcript.state,
                selected_version_id=transcript.selected_version_id,
                segment_count=transcript.segment_count,
                gap_count=transcript.gap_count,
                timeline_url=(
                    f"{base}/transcript?transcript_version_id={transcript.selected_version_id}"
                    if transcript.selected_version_id is not None
                    else f"{base}/transcript"
                ),
                versions_url=f"{base}/transcript/versions",
            ),
            summary=summary,
            questions=RecordCollectionIndex(
                total_count=question_count, list_url=f"{base}/questions?sort=RECENT"
            ),
            question_clusters=RecordQuestionClustersIndex(
                state=clustering_state[0],
                current=RecordCollectionIndex(
                    total_count=clustering_state[1],
                    list_url=f"{base}/question-clusters?scope=CURRENT",
                ),
                final=RecordCollectionIndex(
                    total_count=clustering_state[2],
                    list_url=f"{base}/question-clusters?scope=FINAL",
                ),
            ),
            answers=RecordCollectionIndex(total_count=answer_count, list_url=f"{base}/answers"),
            jobs=RecordCollectionIndex(total_count=shared_job_count, list_url=f"{base}/jobs"),
        )

    async def _transcript_index(
        self, session: AsyncSession, lecture_session: LectureSession
    ) -> _TranscriptProjection:
        versions = list(
            await session.scalars(
                select(TranscriptVersion)
                .where(TranscriptVersion.session_id == lecture_session.id)
                .order_by(TranscriptVersion.version.desc(), TranscriptVersion.id.desc())
            )
        )
        if not versions:
            return _TranscriptProjection(None, None, 0, 0)
        current = versions[0]
        canonical = next(
            (
                version
                for version in versions
                if version.id == lecture_session.canonical_transcript_version_id
            ),
            None,
        )
        selected = canonical or current
        # Keep the public aggregate identical to the existing transcript endpoint.
        state = TranscriptService._project_version
        current_projection = state(current, lecture_session)
        canonical_projection = state(canonical, lecture_session) if canonical is not None else None
        from tbd.schemas.transcripts import TranscriptAggregateResponse

        aggregate_response = TranscriptAggregateResponse(
            session_id=lecture_session.id,
            status=current.status,
            current_version=current_projection,
            canonical_version_id=lecture_session.canonical_transcript_version_id,
            canonical_version=canonical_projection,
            updated_at=max(current.updated_at, lecture_session.updated_at),
        )
        segment_count = await self._count(
            session,
            select(func.count())
            .select_from(TranscriptSegment)
            .where(TranscriptSegment.transcript_version_id == selected.id),
        )
        gap_count = await self._count(
            session,
            select(func.count())
            .select_from(TranscriptGap)
            .where(TranscriptGap.transcript_version_id == selected.id),
        )
        return _TranscriptProjection(aggregate_response, selected.id, segment_count, gap_count)

    async def _summary_index(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        user_id: UUID,
    ) -> RecordSummaryIndex:
        summaries, status, reason = await PersonalAIService().list_summaries(
            session,
            session_id=lecture_session.id,
            user_id=user_id,
            summary_type="FINAL",
            limit=1,
        )
        reason_response = self._summary_reason(reason)
        return RecordSummaryIndex(
            state=FinalSummaryState(status=status, reason=reason_response),
            summary_url=(f"/api/v1/summaries/{summaries[0].id}" if summaries else None),
            summaries_url=f"/api/v1/sessions/{lecture_session.id}/summaries?summary_type=FINAL",
        )

    @staticmethod
    def _summary_reason(reason: dict[str, str] | None) -> FinalSummaryReason | None:
        if reason is None:
            return None
        code = reason.get("code")
        if code == "NO_FINAL_TRANSCRIPT":
            return FinalSummaryReason(code=code, message="요약할 강의 내용이 없습니다.")
        if code == "SUMMARY_SOURCE_UNAVAILABLE":
            return FinalSummaryReason(
                code=code, message="Transcript 처리 문제로 요약을 만들지 못했습니다."
            )
        return None

    async def _clustering_state(
        self, session: AsyncSession, lecture_session: LectureSession
    ) -> tuple[object, int, int]:
        state = await session.get(QuestionClusteringState, lecture_session.id)
        if state is None:
            # The state row is created atomically with the Session.  Keeping this
            # failure explicit prevents an invented empty clustering projection.
            raise RecordNotFoundError
        active = await session.scalar(
            select(AIJob)
            .where(
                AIJob.session_id == lecture_session.id,
                AIJob.job_type == "QUESTION_CLUSTERING",
                AIJob.status.in_(("PENDING", "RUNNING")),
            )
            .order_by(AIJob.created_at.desc(), AIJob.id.desc())
        )
        last = (
            await session.get(AIJob, state.last_job_id) if state.last_job_id is not None else None
        )
        current_count = await self._cluster_count(
            session, lecture_session.id, state.current_generation
        )
        final_count = await self._cluster_count(session, lecture_session.id, state.final_generation)
        return (
            QuestionService.project_clustering_state(state, active=active, last=last),
            current_count,
            final_count,
        )

    async def _cluster_count(
        self, session: AsyncSession, session_id: UUID, generation: int | None
    ) -> int:
        if generation is None:
            return 0
        return await self._count(
            session,
            select(func.count())
            .select_from(QuestionCluster)
            .where(
                QuestionCluster.session_id == session_id, QuestionCluster.generation == generation
            ),
        )

    @staticmethod
    async def _count(session: AsyncSession, statement: object) -> int:
        value = await session.scalar(statement)  # type: ignore[arg-type]
        return int(value or 0)
