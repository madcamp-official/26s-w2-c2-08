"""Fenced LIVE incremental Question clustering worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.jobs.kernel import JobKernel
from tbd.models.clustering import (
    AIRepresentativeQuestion,
    Answer,
    QuestionCluster,
    QuestionClusterMember,
)
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility, LectureSessionStatus
from tbd.models.questions import AIJob, Question, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.providers.ai.clustering import (
    ClusteringInput,
    ClusterSuggestion,
    QuestionClusteringProvider,
)
from tbd.repositories.jobs import ClaimedJob
from tbd.repositories.outbox import OutboxRepository
from tbd.services.postprocessing import evaluate_session_completion
from tbd.services.questions import QuestionService

CLUSTERING_LEASE = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class ClaimedClusteringWork:
    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID
    input_through_sequence: int
    base_revision: int
    mode: str
    inputs: tuple[ClusteringInput, ...]
    member_kinds: dict[UUID, str]


class QuestionClusteringWorker:
    """Process immutable LIVE and final Question-clustering snapshots."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: QuestionClusteringProvider,
        *,
        kernel: JobKernel | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider
        self.kernel = kernel or JobKernel()
        self.outbox = outbox or OutboxRepository()

    async def run_once(self, *, now: datetime | None = None) -> bool:
        timestamp = now or datetime.now(UTC)
        await self._requeue_one_retry(timestamp)
        claimed = await self._claim(timestamp)
        if claimed is None:
            return False
        try:
            suggestions = await self.provider.cluster(claimed.inputs)
            self._validate_partition(claimed.inputs, suggestions)
        except Exception:
            await self._fail(claimed, timestamp)
        else:
            await self._succeed(claimed, suggestions, timestamp)
        return True

    async def _claim(self, now: datetime) -> ClaimedClusteringWork | None:
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(AIJob)
                    .where(
                        AIJob.job_type == AIJobType.QUESTION_CLUSTERING,
                        AIJob.clustering_mode.in_(("LIVE_INCREMENTAL", "FINAL")),
                        AIJob.status == AIJobStatus.PENDING,
                        AIJob.available_at <= now,
                    )
                    .order_by(AIJob.available_at, AIJob.created_at)
                    .limit(1)
                )
                if job is None:
                    return None
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == job.session_id)
                    .with_for_update()
                )
                state = await session.scalar(
                    select(QuestionClusteringState)
                    .where(QuestionClusteringState.session_id == job.session_id)
                    .with_for_update()
                )
                if (
                    lecture_session is None
                    or state is None
                    or job.input_through_sequence is None
                    or job.base_revision is None
                    or not self._session_allows_mode(lecture_session, job.clustering_mode)
                ):
                    await self.kernel.supersede(session, job.id, now=now)
                    return None
                run = await self.kernel.claim_shared_by_id(
                    session,
                    job.id,
                    now=now,
                    lease_duration=CLUSTERING_LEASE,
                    job_type=AIJobType.QUESTION_CLUSTERING,
                )
                if run is None:
                    return None
                state.last_job_id = job.id
                state.last_job_attempt = job.attempt
                state.last_job_status = str(AIJobStatus.RUNNING)
                await self._emit_state(session, state, active=job)
                questions = tuple(
                    await session.scalars(
                        select(Question)
                        .where(
                            Question.session_id == job.session_id,
                            Question.clustering_sequence
                            > (
                                state.applied_sequence
                                if job.clustering_mode == "LIVE_INCREMENTAL"
                                else 0
                            ),
                            Question.clustering_sequence <= job.input_through_sequence,
                        )
                        .order_by(Question.clustering_sequence)
                    )
                )
                member_kinds = {question.id: "QUESTION" for question in questions}
                inputs = [
                    ClusteringInput(question_id=question.id, content=question.content)
                    for question in questions
                ]
                if job.clustering_mode == "FINAL" and job.final_answered_through_at is not None:
                    representatives = list(
                        await session.scalars(
                            select(AIRepresentativeQuestion)
                            .join(
                                Answer,
                                Answer.target_representative_question_id
                                == AIRepresentativeQuestion.id,
                            )
                            .where(
                                AIRepresentativeQuestion.session_id == job.session_id,
                                Answer.session_id == job.session_id,
                                Answer.status == "COMPLETED",
                                Answer.completed_at <= job.final_answered_through_at,
                            )
                            .order_by(
                                AIRepresentativeQuestion.created_at, AIRepresentativeQuestion.id
                            )
                        )
                    )
                    for representative in representatives:
                        member_kinds[representative.id] = "REPRESENTATIVE"
                        inputs.append(
                            ClusteringInput(
                                question_id=representative.id,
                                content=representative.text,
                            )
                        )
                return ClaimedClusteringWork(
                    job_id=run.job_id,
                    session_id=run.session_id,
                    attempt=run.attempt,
                    run_token=run.run_token,
                    input_through_sequence=job.input_through_sequence,
                    base_revision=job.base_revision,
                    mode=str(job.clustering_mode),
                    inputs=tuple(inputs),
                    member_kinds=member_kinds,
                )

    async def _requeue_one_retry(self, now: datetime) -> bool:
        """Move one retry-reserved LIVE row to its next fenced attempt.

        The retry preserves the original watermark and revision.  Questions
        committed while it is reserved remain coalesced for the fresh Job
        created only after this attempt succeeds.
        """

        async with self.session_factory() as session:
            async with session.begin():
                candidate = await session.execute(
                    select(QuestionClusteringState.session_id, QuestionClusteringState.retry_job_id)
                    .where(QuestionClusteringState.retry_job_id.is_not(None))
                    .order_by(
                        QuestionClusteringState.updated_at, QuestionClusteringState.session_id
                    )
                    .limit(1)
                )
                row = candidate.first()
                if row is None or row.retry_job_id is None:
                    return False
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == row.session_id)
                    .with_for_update()
                )
                state = await session.scalar(
                    select(QuestionClusteringState)
                    .where(QuestionClusteringState.session_id == row.session_id)
                    .with_for_update()
                )
                if (
                    lecture_session is None
                    or state is None
                    or state.retry_job_id != row.retry_job_id
                ):
                    return False
                if lecture_session.status != LectureSessionStatus.LIVE:
                    await self.kernel.supersede(session, row.retry_job_id, now=now)
                    state.retry_job_id = None
                    state.last_job_status = str(AIJobStatus.SUPERSEDED)
                    await self._emit_state(session, state, active=None)
                    return True
                job = await session.get(AIJob, row.retry_job_id, with_for_update=True)
                if (
                    job is None
                    or job.status != AIJobStatus.FAILED
                    or job.clustering_mode != "LIVE_INCREMENTAL"
                    or job.input_through_sequence is None
                    or job.base_revision != state.current_revision
                    or job.input_through_sequence <= state.applied_sequence
                ):
                    return False
                requeued = await self.kernel.retry_failed(session, job.id, now=now)
                if requeued is None:
                    return False
                state.retry_job_id = None
                state.last_job_id = requeued.id
                state.last_job_attempt = requeued.attempt
                state.last_job_status = str(AIJobStatus.PENDING)
                await self._emit_state(session, state, active=requeued)
                return True

    async def _succeed(
        self,
        claimed: ClaimedClusteringWork,
        suggestions: tuple[ClusterSuggestion, ...],
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == claimed.session_id)
                    .with_for_update()
                )
                state = await session.scalar(
                    select(QuestionClusteringState)
                    .where(QuestionClusteringState.session_id == claimed.session_id)
                    .with_for_update()
                )
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                if (
                    job is None
                    or job.status != AIJobStatus.RUNNING
                    or job.attempt != claimed.attempt
                    or job.run_token != claimed.run_token
                ):
                    return
                if (
                    lecture_session is None
                    or state is None
                    or not self._session_allows_mode(lecture_session, claimed.mode)
                    or state.current_revision != claimed.base_revision
                ):
                    await self.kernel.supersede(session, job.id, now=now)
                    if state is not None:
                        state.retry_job_id = None
                        state.last_job_id = job.id
                        state.last_job_attempt = job.attempt
                        state.last_job_status = str(AIJobStatus.SUPERSEDED)
                        await self._emit_state(session, state, active=None)
                    return
                if claimed.mode == "FINAL":
                    await self._succeed_final(
                        session,
                        lecture_session=lecture_session,
                        state=state,
                        job=job,
                        claimed=claimed,
                        suggestions=suggestions,
                        now=now,
                    )
                    return

                generation = (state.current_generation or 0) + 1
                previous = (
                    list(
                        await session.scalars(
                            select(QuestionCluster)
                            .where(
                                QuestionCluster.session_id == claimed.session_id,
                                QuestionCluster.generation == state.current_generation,
                            )
                            .order_by(QuestionCluster.ordinal)
                        )
                    )
                    if state.current_generation
                    else []
                )
                ordinal = 0
                for old in previous:
                    copied = QuestionCluster(
                        logical_cluster_id=old.logical_cluster_id,
                        session_id=old.session_id,
                        representative_question_id=old.representative_question_id,
                        generation=generation,
                        ordinal=ordinal,
                        is_final=False,
                        created_by_job_id=job.id,
                        created_by_job_attempt=job.attempt,
                    )
                    session.add(copied)
                    await session.flush()
                    members = await session.scalars(
                        select(QuestionClusterMember)
                        .where(QuestionClusterMember.cluster_id == old.id)
                        .order_by(QuestionClusterMember.position)
                    )
                    for member in members:
                        session.add(
                            QuestionClusterMember(
                                cluster_id=copied.id,
                                session_id=copied.session_id,
                                generation=generation,
                                position=member.position,
                                question_id=member.question_id,
                                representative_question_id=member.representative_question_id,
                            )
                        )
                    ordinal += 1
                for suggestion in suggestions:
                    representative = AIRepresentativeQuestion(
                        session_id=claimed.session_id,
                        text=suggestion.representative,
                        status="OPEN",
                        lifecycle_status="ACTIVE",
                        created_by_job_id=job.id,
                        created_by_job_attempt=job.attempt,
                        created_in_generation=generation,
                        version=1,
                    )
                    session.add(representative)
                    await session.flush()
                    cluster = QuestionCluster(
                        logical_cluster_id=uuid4(),
                        session_id=claimed.session_id,
                        representative_question_id=representative.id,
                        generation=generation,
                        ordinal=ordinal,
                        is_final=False,
                        created_by_job_id=job.id,
                        created_by_job_attempt=job.attempt,
                    )
                    session.add(cluster)
                    await session.flush()
                    for position, question_id in enumerate(suggestion.question_ids):
                        session.add(
                            QuestionClusterMember(
                                cluster_id=cluster.id,
                                session_id=claimed.session_id,
                                generation=generation,
                                position=position,
                                question_id=question_id,
                            )
                        )
                    ordinal += 1
                run = self._run_from_job(job)
                if not await self.kernel.succeed(session, run, now=now):
                    return
                state.applied_sequence = claimed.input_through_sequence
                state.current_revision += 1
                state.current_generation = generation
                state.last_job_id, state.last_job_attempt, state.last_job_status = (
                    job.id,
                    job.attempt,
                    "SUCCEEDED",
                )
                state.retry_job_id = None
                for old in previous:
                    await session.delete(old)
                next_job = await self._enqueue_next_job(session, state)
                await self._emit_state(session, state, active=next_job)

    async def _fail(self, claimed: ClaimedClusteringWork, now: datetime) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                state = await session.scalar(
                    select(QuestionClusteringState)
                    .where(QuestionClusteringState.session_id == claimed.session_id)
                    .with_for_update()
                )
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == claimed.session_id)
                    .with_for_update()
                )
                if (
                    job is None
                    or state is None
                    or job.attempt != claimed.attempt
                    or job.run_token != claimed.run_token
                ):
                    return
                if job.status != AIJobStatus.RUNNING:
                    return
                if (
                    lecture_session is None
                    or not self._session_allows_mode(lecture_session, claimed.mode)
                    or state.current_revision != claimed.base_revision
                ):
                    await self.kernel.supersede(session, job.id, now=now)
                    state.retry_job_id = None
                    state.last_job_id = job.id
                    state.last_job_attempt = job.attempt
                    state.last_job_status = str(AIJobStatus.SUPERSEDED)
                    await self._emit_state(session, state, active=None)
                    return
                run = self._run_from_job(job)
                if await self.kernel.fail(
                    session,
                    run,
                    error_code="QUESTION_CLUSTERING_FAILED",
                    error_message="질문 분류를 완료하지 못했습니다.",
                    retryable=True,
                    now=now,
                ):
                    if claimed.mode == "FINAL":
                        state.last_job_id, state.last_job_attempt, state.last_job_status = (
                            job.id,
                            job.attempt,
                            "FAILED",
                        )
                        await self._emit_state(session, state, active=None)
                        await evaluate_session_completion(
                            session,
                            session_id=claimed.session_id,
                            now=now,
                            outbox=self.outbox,
                        )
                        return
                    state.retry_job_id = job.id
                    state.last_job_id, state.last_job_attempt, state.last_job_status = (
                        job.id,
                        job.attempt,
                        "FAILED",
                    )
                    await self._emit_state(session, state, active=None)

    async def _succeed_final(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        state: QuestionClusteringState,
        job: AIJob,
        claimed: ClaimedClusteringWork,
        suggestions: tuple[ClusterSuggestion, ...],
        now: datetime,
    ) -> None:
        """Persist an independent final generation without replacing LIVE history."""

        generation = max(state.current_generation or 0, state.final_generation or 0) + 1
        preserved_representative_ids = {
            member_id
            for member_id, kind in claimed.member_kinds.items()
            if kind == "REPRESENTATIVE"
        }
        if preserved_representative_ids:
            representatives = list(
                await session.scalars(
                    select(AIRepresentativeQuestion)
                    .where(AIRepresentativeQuestion.id.in_(preserved_representative_ids))
                    .with_for_update()
                )
            )
            for representative in representatives:
                representative.lifecycle_status = "PRESERVED"
                representative.preserved_at = now
                representative.discarded_at = None
                representative.version += 1
        for ordinal, suggestion in enumerate(suggestions):
            representative = AIRepresentativeQuestion(
                session_id=claimed.session_id,
                text=suggestion.representative,
                status="OPEN",
                lifecycle_status="ACTIVE",
                created_by_job_id=job.id,
                created_by_job_attempt=job.attempt,
                created_in_generation=generation,
                version=1,
            )
            session.add(representative)
            await session.flush()
            cluster = QuestionCluster(
                logical_cluster_id=uuid4(),
                session_id=claimed.session_id,
                representative_question_id=representative.id,
                generation=generation,
                ordinal=ordinal,
                is_final=True,
                finalized_at=now,
                created_by_job_id=job.id,
                created_by_job_attempt=job.attempt,
            )
            session.add(cluster)
            await session.flush()
            for position, input_id in enumerate(suggestion.question_ids):
                kind = claimed.member_kinds[input_id]
                session.add(
                    QuestionClusterMember(
                        cluster_id=cluster.id,
                        session_id=claimed.session_id,
                        generation=generation,
                        position=position,
                        question_id=input_id if kind == "QUESTION" else None,
                        representative_question_id=(input_id if kind == "REPRESENTATIVE" else None),
                    )
                )
        if not await self.kernel.succeed(session, self._run_from_job(job), now=now):
            return
        state.current_generation = generation
        state.current_revision += 1
        state.final_generation = generation
        state.last_job_id = job.id
        state.last_job_attempt = job.attempt
        state.last_job_status = "SUCCEEDED"
        await self._emit_state(session, state, active=None)
        await evaluate_session_completion(
            session,
            session_id=lecture_session.id,
            now=now,
            outbox=self.outbox,
        )

    async def _enqueue_next_job(
        self, session: AsyncSession, state: QuestionClusteringState
    ) -> AIJob | None:
        """Schedule exactly one fresh watermark after a successful coalesced run."""

        if state.requested_sequence <= state.applied_sequence:
            return None
        next_job = AIJob(
            session_id=state.session_id,
            job_type=AIJobType.QUESTION_CLUSTERING,
            visibility=AIJobVisibility.SHARED,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            clustering_mode="LIVE_INCREMENTAL",
            input_through_sequence=state.requested_sequence,
            base_revision=state.current_revision,
            blocks_session_completion=False,
            retryable=True,
        )
        await self.kernel.enqueue(session, next_job)
        state.last_job_id = next_job.id
        state.last_job_attempt = next_job.attempt
        state.last_job_status = str(AIJobStatus.PENDING)
        return next_job

    async def _emit_state(
        self,
        session: AsyncSession,
        state: QuestionClusteringState,
        *,
        active: AIJob | None,
    ) -> None:
        last = (
            active
            if active is not None and active.id == state.last_job_id
            else await session.get(AIJob, state.last_job_id)
            if state.last_job_id is not None
            else None
        )
        payload = QuestionService.project_clustering_state(
            state, active=active, last=last
        ).model_dump(mode="json")
        await self.outbox.enqueue(
            session,
            session_id=state.session_id,
            partition_key=f"session:{state.session_id}",
            event_type="clustering.updated",
            resource_version=max(1, state.requested_sequence),
            payload={"clustering_state": payload},
        )

    @staticmethod
    def _run_from_job(job: AIJob) -> ClaimedJob:
        if job.run_token is None:
            raise ValueError("running clustering job is missing its run token")
        return ClaimedJob(
            job_id=job.id,
            session_id=job.session_id,
            attempt=job.attempt,
            run_token=job.run_token,
            job_type=str(job.job_type),
        )

    @staticmethod
    def _session_allows_mode(lecture_session: LectureSession, mode: str | None) -> bool:
        if mode == "LIVE_INCREMENTAL":
            return lecture_session.status == LectureSessionStatus.LIVE
        if mode == "FINAL":
            return lecture_session.status in (
                LectureSessionStatus.PROCESSING,
                LectureSessionStatus.COMPLETED,
            )
        return False

    @staticmethod
    def _validate_partition(
        inputs: tuple[ClusteringInput, ...], suggestions: tuple[ClusterSuggestion, ...]
    ) -> None:
        expected = {item.question_id for item in inputs}
        actual = [
            question_id for suggestion in suggestions for question_id in suggestion.question_ids
        ]
        if set(actual) != expected or len(actual) != len(set(actual)):
            raise ValueError("clustering output must partition inputs exactly once")
