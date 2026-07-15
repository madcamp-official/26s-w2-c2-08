"""Durable Session postprocessing coordination and final AI workers.

The coordinator intentionally owns only short database transactions.  Batch
STT, clustering, embedding, and LLM calls remain in their respective workers;
this module turns their terminal records into the next immutable work item and
uses the persisted blocking ledger—not an in-memory DAG—to complete a class.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.jobs.kernel import JobKernel
from tbd.models.clustering import Answer, AnswerOrganization, AnswerTranscriptMapping
from tbd.models.enums import (
    AIJobStatus,
    AIJobType,
    AIJobVisibility,
    LectureSessionStatus,
    SummaryType,
    SummaryVisibility,
    TranscriptSource,
    TranscriptStatus,
)
from tbd.models.knowledge import LectureSummary
from tbd.models.materials import (
    RecordingUpload,
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.models.questions import AIJob, Question, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.providers.ai import AIProviderError, LLMGenerationRequest, LLMMessage, LLMProvider
from tbd.repositories.jobs import ClaimedJob
from tbd.repositories.outbox import OutboxRepository
from tbd.schemas.jobs import project_ai_job
from tbd.schemas.sessions import LectureSessionResponse
from tbd.services.knowledge import enqueue_knowledge_indexing
from tbd.services.questions import QuestionService

COORDINATOR_LEASE = timedelta(minutes=1)
FINAL_AI_LEASE = timedelta(minutes=1)
FINAL_AI_TIMEOUT = timedelta(seconds=15)
PROCESSING_DEADLINE = timedelta(minutes=10)
FINAL_SUMMARY_PROMPT_VERSION = "final-summary-v1"
ANSWER_ORGANIZATION_PROMPT_VERSION = "answer-organization-v1"


@dataclass(frozen=True, slots=True)
class _ClaimedCoordinator:
    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID


@dataclass(frozen=True, slots=True)
class _ClaimedFinalAI:
    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID
    job_type: str
    answer_id: UUID | None = None


async def requeue_completed_coordinator(
    session: AsyncSession,
    *,
    lecture_session: LectureSession,
    now: datetime,
    outbox: OutboxRepository | None = None,
) -> AIJob | None:
    """Reopen the one coordinator after a successful HQ retry.

    This is intentionally not the public generic retry path: a successful HQ
    retry after ``COMPLETED`` must rebuild mappings without regressing the
    Session state.  The same coordinator row receives ``attempt + 1``.
    """

    if lecture_session.status != LectureSessionStatus.COMPLETED:
        return None
    job = await session.scalar(
        select(AIJob)
        .where(
            AIJob.session_id == lecture_session.id,
            AIJob.job_type == AIJobType.SESSION_POSTPROCESSING,
        )
        .with_for_update()
    )
    if job is None or job.status in (AIJobStatus.PENDING, AIJobStatus.RUNNING):
        return None
    job.status = AIJobStatus.PENDING
    job.attempt += 1
    job.version += 1
    job.available_at = now
    job.run_token = None
    job.lease_expires_at = None
    job.progress_stage = None
    job.progress_percent = None
    job.retryable = False
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    await session.flush()
    await (outbox or OutboxRepository()).enqueue(
        session,
        session_id=job.session_id,
        partition_key=f"session:{job.session_id}",
        event_type="job.updated",
        resource_version=job.version,
        payload=project_ai_job(job).model_dump(mode="json"),
    )
    return job


async def evaluate_session_completion(
    session: AsyncSession,
    *,
    session_id: UUID,
    now: datetime,
    outbox: OutboxRepository | None = None,
) -> bool:
    """Move PROCESSING to COMPLETED only when the stored predicate is terminal."""

    lecture_session = await session.scalar(
        select(LectureSession).where(LectureSession.id == session_id).with_for_update()
    )
    if lecture_session is None or lecture_session.status != LectureSessionStatus.PROCESSING:
        return False
    coordinator = await session.scalar(
        select(AIJob)
        .where(
            AIJob.session_id == session_id,
            AIJob.job_type == AIJobType.SESSION_POSTPROCESSING,
        )
        .with_for_update()
    )
    if coordinator is None or coordinator.status in (AIJobStatus.PENDING, AIJobStatus.RUNNING):
        return False
    blocking_active = await session.scalar(
        select(AIJob.id).where(
            AIJob.session_id == session_id,
            AIJob.blocks_session_completion.is_(True),
            AIJob.status.in_((AIJobStatus.PENDING, AIJobStatus.RUNNING)),
        )
    )
    if blocking_active is not None:
        return False
    if not await _source_gate_is_terminal(session, lecture_session):
        return False
    lecture_session.status = LectureSessionStatus.COMPLETED
    lecture_session.completed_at = now
    lecture_session.version += 1
    await session.flush()
    await (outbox or OutboxRepository()).enqueue(
        session,
        session_id=lecture_session.id,
        partition_key=f"session:{lecture_session.id}",
        event_type="session.updated",
        resource_version=lecture_session.version,
        payload=LectureSessionResponse.model_validate(lecture_session).model_dump(mode="json"),
    )
    return True


async def _source_gate_is_terminal(session: AsyncSession, lecture_session: LectureSession) -> bool:
    """Return whether recording/HQ (or no-recording LIVE) can no longer progress."""

    recording = await session.scalar(
        select(SessionRecording)
        .where(SessionRecording.session_id == lecture_session.id)
        .with_for_update()
    )
    if recording is None:
        live = await session.scalar(
            select(TranscriptVersion)
            .where(
                TranscriptVersion.session_id == lecture_session.id,
                TranscriptVersion.source == TranscriptSource.LIVE,
            )
            .order_by(TranscriptVersion.version.desc())
            .with_for_update()
        )
        return live is not None and live.status in (
            TranscriptStatus.FINALIZED,
            TranscriptStatus.EMPTY,
            TranscriptStatus.FAILED,
        )
    if recording.status == "FAILED":
        return True
    if recording.status != "UPLOADED":
        return False
    version = await _latest_recording_version(session, lecture_session.id)
    return version is not None and version.status in (
        TranscriptStatus.FINALIZED,
        TranscriptStatus.EMPTY,
        TranscriptStatus.FAILED,
    )


async def _latest_recording_version(
    session: AsyncSession, session_id: UUID
) -> TranscriptVersion | None:
    return await session.scalar(
        select(TranscriptVersion)
        .where(
            TranscriptVersion.session_id == session_id,
            TranscriptVersion.source == TranscriptSource.RECORDING,
        )
        .order_by(TranscriptVersion.version.desc())
        .with_for_update()
    )


class SessionPostprocessingWorker:
    """Schedule and execute the non-STT terminal stages of a class."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_provider: LLMProvider,
        *,
        kernel: JobKernel | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.llm_provider = llm_provider
        self.outbox = outbox or OutboxRepository()
        self.kernel = kernel or JobKernel(outbox=self.outbox)

    async def run_once(self, *, now: datetime | None = None) -> bool:
        timestamp = now or datetime.now(UTC)
        if await self.run_watchdog_once(now=timestamp):
            return True
        coordinator = await self._claim_coordinator(timestamp)
        if coordinator is not None:
            await self._finish_coordinator(coordinator, now=timestamp)
            return True
        answer_work = await self._claim_final_ai(AIJobType.ANSWER_ORGANIZATION, timestamp)
        if answer_work is not None:
            await self._run_answer_organization(answer_work, now=timestamp)
            return True
        summary_work = await self._claim_final_ai(AIJobType.FINAL_SUMMARY, timestamp)
        if summary_work is not None:
            await self._run_final_summary(summary_work, now=timestamp)
            return True
        return False

    async def _claim_coordinator(self, now: datetime) -> _ClaimedCoordinator | None:
        async with self.session_factory() as session:
            async with session.begin():
                candidate = await session.scalar(
                    select(AIJob)
                    .where(
                        AIJob.job_type == AIJobType.SESSION_POSTPROCESSING,
                        AIJob.status == AIJobStatus.PENDING,
                        AIJob.available_at <= now,
                    )
                    .order_by(AIJob.available_at, AIJob.created_at, AIJob.id)
                    .limit(1)
                )
                if candidate is None:
                    return None
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == candidate.session_id)
                    .with_for_update()
                )
                if lecture_session is None or not await _source_gate_is_terminal(
                    session, lecture_session
                ):
                    return None
                run = await self.kernel.claim_shared_by_id(
                    session,
                    candidate.id,
                    now=now,
                    lease_duration=COORDINATOR_LEASE,
                    job_type=AIJobType.SESSION_POSTPROCESSING,
                )
                if run is None:
                    return None
                return _ClaimedCoordinator(
                    job_id=run.job_id,
                    session_id=run.session_id,
                    attempt=run.attempt,
                    run_token=run.run_token,
                )

    async def _finish_coordinator(self, claimed: _ClaimedCoordinator, *, now: datetime) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == claimed.session_id)
                    .with_for_update()
                )
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                if lecture_session is None or job is None or not self._is_current(job, claimed):
                    return
                if not await _source_gate_is_terminal(session, lecture_session):
                    await self.kernel.fail(
                        session,
                        self._as_run(claimed, AIJobType.SESSION_POSTPROCESSING),
                        error_code="POSTPROCESSING_SOURCE_NOT_READY",
                        error_message="후처리 입력을 아직 확정할 수 없습니다.",
                        retryable=True,
                        now=now,
                    )
                    return

                version = await _latest_recording_version(session, lecture_session.id)
                finalized = (
                    version is not None
                    and version.status == TranscriptStatus.FINALIZED
                    and version.last_sequence > 0
                )
                if finalized:
                    await self._rebuild_answer_mappings(
                        session,
                        lecture_session=lecture_session,
                        target_version=version,
                        job=job,
                        now=now,
                    )
                    await enqueue_knowledge_indexing(
                        session,
                        session_id=lecture_session.id,
                        kernel=self.kernel,
                    )
                await self._schedule_answer_organizations(
                    session,
                    lecture_session=lecture_session,
                    target_version=version if finalized else None,
                )
                if finalized:
                    await self._schedule_final_summary(
                        session,
                        lecture_session=lecture_session,
                        source_version=version,
                    )
                if not await self.kernel.succeed(
                    session,
                    self._as_run(claimed, AIJobType.SESSION_POSTPROCESSING),
                    now=now,
                ):
                    return
                await evaluate_session_completion(
                    session,
                    session_id=lecture_session.id,
                    now=now,
                    outbox=self.outbox,
                )

    async def _rebuild_answer_mappings(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        target_version: TranscriptVersion,
        job: AIJob,
        now: datetime,
    ) -> None:
        answers = list(
            await session.scalars(
                select(Answer)
                .where(
                    Answer.session_id == lecture_session.id,
                    Answer.status == "COMPLETED",
                    Answer.source_transcript_version_id.is_not(None),
                )
                .order_by(Answer.started_at, Answer.id)
                .with_for_update()
            )
        )
        for answer in answers:
            mapping = await session.scalar(
                select(AnswerTranscriptMapping)
                .where(
                    AnswerTranscriptMapping.answer_id == answer.id,
                    AnswerTranscriptMapping.target_transcript_version_id == target_version.id,
                )
                .with_for_update()
            )
            if mapping is not None and mapping.status == "SUCCEEDED":
                continue
            if mapping is None:
                mapping = AnswerTranscriptMapping(
                    answer_id=answer.id,
                    target_transcript_version_id=target_version.id,
                    session_id=lecture_session.id,
                    status="PENDING",
                )
                session.add(mapping)
                await session.flush()
            source_start = await session.get(TranscriptSegment, answer.start_segment_id)
            source_end = await session.get(TranscriptSegment, answer.end_segment_id)
            mapped = []
            if source_start is not None and source_end is not None:
                mapped = list(
                    await session.scalars(
                        select(TranscriptSegment)
                        .where(
                            TranscriptSegment.transcript_version_id == target_version.id,
                            TranscriptSegment.end_ms >= source_start.start_ms,
                            TranscriptSegment.start_ms <= source_end.end_ms,
                        )
                        .order_by(TranscriptSegment.sequence)
                    )
                )
            mapping.processed_by_job_id = job.id
            mapping.processed_by_job_attempt = job.attempt
            if mapped:
                mapping.status = "SUCCEEDED"
                mapping.mapped_start_segment_id = mapped[0].id
                mapping.mapped_end_segment_id = mapped[-1].id
                mapping.mapped_at = now
                mapping.failed_at = None
            else:
                mapping.status = "FAILED"
                mapping.mapped_start_segment_id = None
                mapping.mapped_end_segment_id = None
                mapping.mapped_at = None
                mapping.failed_at = now

    async def _schedule_answer_organizations(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        target_version: TranscriptVersion | None,
    ) -> None:
        answers = list(
            await session.scalars(
                select(Answer)
                .where(
                    Answer.session_id == lecture_session.id,
                    Answer.status == "COMPLETED",
                    Answer.source_transcript_version_id.is_not(None),
                )
                .order_by(Answer.started_at, Answer.id)
                .with_for_update()
            )
        )
        for answer in answers:
            existing = await session.scalar(
                select(AIJob)
                .where(
                    AIJob.job_type == AIJobType.ANSWER_ORGANIZATION,
                    AIJob.target_answer_id == answer.id,
                )
                .with_for_update()
            )
            if existing is not None:
                continue
            source_version_id = answer.source_transcript_version_id
            start_id = answer.start_segment_id
            end_id = answer.end_segment_id
            if target_version is not None:
                mapping = await session.scalar(
                    select(AnswerTranscriptMapping).where(
                        AnswerTranscriptMapping.answer_id == answer.id,
                        AnswerTranscriptMapping.target_transcript_version_id == target_version.id,
                        AnswerTranscriptMapping.status == "SUCCEEDED",
                    )
                )
                if mapping is not None:
                    source_version_id = target_version.id
                    start_id = mapping.mapped_start_segment_id
                    end_id = mapping.mapped_end_segment_id
            if source_version_id is None or start_id is None or end_id is None:
                continue
            await self.kernel.enqueue(
                session,
                AIJob(
                    session_id=lecture_session.id,
                    job_type=AIJobType.ANSWER_ORGANIZATION,
                    visibility=AIJobVisibility.SHARED,
                    status=AIJobStatus.PENDING,
                    attempt=1,
                    version=1,
                    target_answer_id=answer.id,
                    input_transcript_version_id=source_version_id,
                    input_start_segment_id=start_id,
                    input_end_segment_id=end_id,
                    blocks_session_completion=True,
                    retryable=True,
                ),
            )

    async def _schedule_final_summary(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        source_version: TranscriptVersion,
    ) -> None:
        active = await session.scalar(
            select(AIJob)
            .where(
                AIJob.session_id == lecture_session.id,
                AIJob.job_type == AIJobType.FINAL_SUMMARY,
                AIJob.status.in_((AIJobStatus.PENDING, AIJobStatus.RUNNING)),
            )
            .with_for_update()
        )
        if active is not None:
            return
        latest_summary = await session.scalar(
            select(LectureSummary)
            .where(
                LectureSummary.session_id == lecture_session.id,
                LectureSummary.summary_type == SummaryType.FINAL,
            )
            .order_by(LectureSummary.created_at.desc(), LectureSummary.id.desc())
            .with_for_update()
        )
        if (
            latest_summary is not None
            and latest_summary.source_transcript_version_id == source_version.id
        ):
            return
        await self.kernel.enqueue(
            session,
            AIJob(
                session_id=lecture_session.id,
                job_type=AIJobType.FINAL_SUMMARY,
                visibility=AIJobVisibility.SHARED,
                status=AIJobStatus.PENDING,
                attempt=1,
                version=1,
                blocks_session_completion=True,
                retryable=True,
            ),
        )

    async def _claim_final_ai(self, job_type: str, now: datetime) -> _ClaimedFinalAI | None:
        async with self.session_factory() as session:
            async with session.begin():
                candidate = await session.scalar(
                    select(AIJob)
                    .where(
                        AIJob.job_type == job_type,
                        AIJob.status == AIJobStatus.PENDING,
                        AIJob.available_at <= now,
                    )
                    .order_by(AIJob.available_at, AIJob.created_at, AIJob.id)
                    .limit(1)
                )
                if candidate is None:
                    return None
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == candidate.session_id)
                    .with_for_update()
                )
                if lecture_session is None:
                    return None
                answer = None
                if job_type == AIJobType.ANSWER_ORGANIZATION:
                    if candidate.target_answer_id is None:
                        return None
                    answer = await session.scalar(
                        select(Answer)
                        .where(Answer.id == candidate.target_answer_id)
                        .with_for_update()
                    )
                    if answer is None or answer.status != "COMPLETED":
                        return None
                run = await self.kernel.claim_shared_by_id(
                    session,
                    candidate.id,
                    now=now,
                    lease_duration=FINAL_AI_LEASE,
                    job_type=job_type,
                )
                if run is None:
                    return None
                return _ClaimedFinalAI(
                    job_id=run.job_id,
                    session_id=run.session_id,
                    attempt=run.attempt,
                    run_token=run.run_token,
                    job_type=job_type,
                    answer_id=answer.id if answer is not None else None,
                )

    async def _run_answer_organization(self, claimed: _ClaimedFinalAI, *, now: datetime) -> None:
        try:
            text = await self._input_text(claimed)
            result = await self.llm_provider.generate(
                LLMGenerationRequest(
                    purpose="answer-organization-v1",
                    prompt_version=ANSWER_ORGANIZATION_PROMPT_VERSION,
                    messages=(LLMMessage(role="user", content=text),),
                ),
                timeout=FINAL_AI_TIMEOUT,
            )
        except AIProviderError as exc:
            await self._fail_final_ai(
                claimed,
                code=str(exc.code),
                retryable=exc.retryable,
                now=now,
            )
            return
        except Exception:
            await self._fail_final_ai(
                claimed,
                code="PROVIDER_INVALID_RESPONSE",
                retryable=False,
                now=now,
            )
            return
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                answer = await session.scalar(
                    select(Answer).where(Answer.id == claimed.answer_id).with_for_update()
                )
                if job is None or answer is None or not self._is_current(job, claimed):
                    return
                existing = await session.scalar(
                    select(AnswerOrganization).where(AnswerOrganization.answer_id == answer.id)
                )
                if existing is None:
                    session.add(
                        AnswerOrganization(
                            answer_id=answer.id,
                            session_id=answer.session_id,
                            content=result.content.strip(),
                            source_transcript_version_id=job.input_transcript_version_id,
                            source_start_segment_id=job.input_start_segment_id,
                            source_end_segment_id=job.input_end_segment_id,
                            created_by_job_id=job.id,
                            created_by_job_attempt=job.attempt,
                            model_name=result.model_name,
                            prompt_version=ANSWER_ORGANIZATION_PROMPT_VERSION,
                        )
                    )
                if await self.kernel.succeed(session, self._as_run(claimed, job.job_type), now=now):
                    await evaluate_session_completion(
                        session, session_id=job.session_id, now=now, outbox=self.outbox
                    )

    async def _run_final_summary(self, claimed: _ClaimedFinalAI, *, now: datetime) -> None:
        try:
            text = await self._input_text(claimed)
            result = await self.llm_provider.generate(
                LLMGenerationRequest(
                    purpose="final-summary-v1",
                    prompt_version=FINAL_SUMMARY_PROMPT_VERSION,
                    messages=(LLMMessage(role="user", content=text),),
                ),
                timeout=FINAL_AI_TIMEOUT,
            )
        except AIProviderError as exc:
            await self._fail_final_ai(claimed, code=str(exc.code), retryable=exc.retryable, now=now)
            return
        except Exception:
            await self._fail_final_ai(
                claimed, code="PROVIDER_INVALID_RESPONSE", retryable=False, now=now
            )
            return
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == claimed.session_id)
                    .with_for_update()
                )
                version = await _latest_recording_version(session, claimed.session_id)
                if (
                    job is None
                    or lecture_session is None
                    or not self._is_current(job, claimed)
                    or version is None
                    or version.status != TranscriptStatus.FINALIZED
                    or version.last_sequence <= 0
                ):
                    return
                first, last = await self._first_last_segment(session, version.id)
                if first is None or last is None:
                    return
                existing = await session.scalar(
                    select(LectureSummary).where(LectureSummary.created_by_job_id == job.id)
                )
                if existing is None:
                    session.add(
                        LectureSummary(
                            session_id=lecture_session.id,
                            requester_user_id=None,
                            created_by_job_id=job.id,
                            created_by_job_attempt=job.attempt,
                            summary_type=SummaryType.FINAL,
                            visibility=SummaryVisibility.COURSE_MEMBERS,
                            content=result.content.strip(),
                            source_transcript_version_id=version.id,
                            source_start_segment_id=first.id,
                            source_end_segment_id=last.id,
                            model_name=result.model_name,
                            prompt_version=FINAL_SUMMARY_PROMPT_VERSION,
                        )
                    )
                if await self.kernel.succeed(session, self._as_run(claimed, job.job_type), now=now):
                    await evaluate_session_completion(
                        session, session_id=job.session_id, now=now, outbox=self.outbox
                    )

    async def _input_text(self, claimed: _ClaimedFinalAI) -> str:
        async with self.session_factory() as session:
            job = await session.get(AIJob, claimed.job_id)
            if job is None:
                raise ValueError("Job is unavailable")
            if job.job_type == AIJobType.ANSWER_ORGANIZATION:
                assert job.input_transcript_version_id is not None
                assert job.input_start_segment_id is not None
                assert job.input_end_segment_id is not None
                start = await session.get(TranscriptSegment, job.input_start_segment_id)
                end = await session.get(TranscriptSegment, job.input_end_segment_id)
                if start is None or end is None:
                    raise ValueError("Answer Transcript input is unavailable")
                segments = list(
                    await session.scalars(
                        select(TranscriptSegment)
                        .where(
                            TranscriptSegment.transcript_version_id
                            == job.input_transcript_version_id,
                            TranscriptSegment.sequence.between(start.sequence, end.sequence),
                        )
                        .order_by(TranscriptSegment.sequence)
                    )
                )
            else:
                version = await _latest_recording_version(session, claimed.session_id)
                if version is None:
                    raise ValueError("Final Transcript input is unavailable")
                segments = list(
                    await session.scalars(
                        select(TranscriptSegment)
                        .where(TranscriptSegment.transcript_version_id == version.id)
                        .order_by(TranscriptSegment.sequence)
                    )
                )
            text = "\n".join(segment.text for segment in segments).strip()
            if not text:
                raise ValueError("Final Transcript input is empty")
            return text

    async def _fail_final_ai(
        self, claimed: _ClaimedFinalAI, *, code: str, retryable: bool, now: datetime
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                if job is None or not self._is_current(job, claimed):
                    return
                if await self.kernel.fail(
                    session,
                    self._as_run(claimed, job.job_type),
                    error_code=code,
                    error_message="후처리 AI 작업을 완료하지 못했습니다.",
                    retryable=retryable,
                    now=now,
                ):
                    await evaluate_session_completion(
                        session, session_id=job.session_id, now=now, outbox=self.outbox
                    )

    async def run_watchdog_once(self, *, now: datetime | None = None) -> bool:
        timestamp = now or datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(
                        LectureSession.status == LectureSessionStatus.PROCESSING,
                        LectureSession.ended_at <= timestamp - PROCESSING_DEADLINE,
                    )
                    .order_by(LectureSession.ended_at, LectureSession.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if lecture_session is None:
                    return False
                await self._force_timeout(session, lecture_session=lecture_session, now=timestamp)
                return True

    async def _force_timeout(
        self, session: AsyncSession, *, lecture_session: LectureSession, now: datetime
    ) -> None:
        recording = await session.scalar(
            select(SessionRecording)
            .where(SessionRecording.session_id == lecture_session.id)
            .with_for_update()
        )
        if recording is not None and recording.status not in ("UPLOADED", "FAILED"):
            recording.status = "FAILED"
            recording.failed_at = now
            recording.live_audio_lease_expires_at = None
            recording.version += 1
        uploads = list(
            await session.scalars(
                select(RecordingUpload)
                .join(SessionRecording, RecordingUpload.recording_id == SessionRecording.id)
                .where(
                    SessionRecording.session_id == lecture_session.id,
                    RecordingUpload.status == "ACTIVE",
                )
                .with_for_update()
            )
        )
        for upload in uploads:
            upload.status = "FAILED"
            upload.terminal_at = now
            upload.version += 1
        await self._terminalize_transcript_source(
            session, lecture_session=lecture_session, recording=recording, now=now
        )
        await self._synthesize_timeout_jobs(session, lecture_session=lecture_session, now=now)
        jobs = list(
            await session.scalars(
                select(AIJob)
                .where(
                    AIJob.session_id == lecture_session.id,
                    AIJob.blocks_session_completion.is_(True),
                    AIJob.status.in_((AIJobStatus.PENDING, AIJobStatus.RUNNING)),
                )
                .with_for_update()
            )
        )
        for job in jobs:
            job.status = AIJobStatus.FAILED
            job.run_token = None
            job.lease_expires_at = None
            job.retryable = True
            job.error_code = "SESSION_PROCESSING_TIMEOUT"
            job.error_message = "수업 후처리 제한 시간을 초과했습니다."
            job.finished_at = now
            job.version += 1
            await self._emit_job(session, job)
        await evaluate_session_completion(
            session, session_id=lecture_session.id, now=now, outbox=self.outbox
        )

    async def _terminalize_transcript_source(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        recording: SessionRecording | None,
        now: datetime,
    ) -> None:
        """Turn a stalled source gate into an explicit fallback terminal state."""

        if recording is None:
            live = await session.scalar(
                select(TranscriptVersion)
                .where(
                    TranscriptVersion.session_id == lecture_session.id,
                    TranscriptVersion.source == TranscriptSource.LIVE,
                )
                .order_by(TranscriptVersion.version.desc())
                .with_for_update()
            )
            if live is not None and live.status == TranscriptStatus.FINALIZING:
                live.status = (
                    TranscriptStatus.FINALIZED if live.last_sequence > 0 else TranscriptStatus.EMPTY
                )
                live.finalized_at = now
            return

        version = await _latest_recording_version(session, lecture_session.id)
        if version is None:
            if recording.status == "UPLOADED":
                recording.status = "FAILED"
                recording.failed_at = now
                recording.version += 1
            return
        if version.status != TranscriptStatus.FINALIZING:
            return
        await session.execute(
            delete(TranscriptSegment).where(TranscriptSegment.transcript_version_id == version.id)
        )
        await session.execute(
            delete(TranscriptGap).where(TranscriptGap.transcript_version_id == version.id)
        )
        version.last_sequence = 0
        version.status = TranscriptStatus.FAILED
        version.failed_at = now

    async def _synthesize_timeout_jobs(
        self, session: AsyncSession, *, lecture_session: LectureSession, now: datetime
    ) -> None:
        """Materialize missing blocking work as terminal failures for observability."""

        assert lecture_session.ended_at is not None
        state = await session.scalar(
            select(QuestionClusteringState)
            .where(QuestionClusteringState.session_id == lecture_session.id)
            .with_for_update()
        )
        final_job = await session.scalar(
            select(AIJob)
            .where(
                AIJob.session_id == lecture_session.id,
                AIJob.job_type == AIJobType.QUESTION_CLUSTERING,
                AIJob.clustering_mode == "FINAL",
            )
            .with_for_update()
        )
        if state is not None and final_job is None:
            question_count = await session.scalar(
                select(func.count(Question.id)).where(
                    Question.session_id == lecture_session.id,
                    Question.clustering_sequence <= state.requested_sequence,
                )
            )
            representative_answer_count = await session.scalar(
                select(func.count(Answer.id)).where(
                    Answer.session_id == lecture_session.id,
                    Answer.status == "COMPLETED",
                    Answer.target_representative_question_id.is_not(None),
                    Answer.completed_at <= lecture_session.ended_at,
                )
            )
            if int(question_count or 0) + int(representative_answer_count or 0) > 0:
                timeout_job = await self._add_timeout_job(
                    session,
                    AIJob(
                        session_id=lecture_session.id,
                        job_type=AIJobType.QUESTION_CLUSTERING,
                        visibility=AIJobVisibility.SHARED,
                        status=AIJobStatus.FAILED,
                        attempt=1,
                        version=1,
                        clustering_mode="FINAL",
                        input_through_sequence=state.requested_sequence,
                        base_revision=state.current_revision,
                        final_answered_through_at=lecture_session.ended_at,
                        blocks_session_completion=True,
                        retryable=True,
                        error_code="SESSION_PROCESSING_TIMEOUT",
                        error_message="수업 후처리 제한 시간을 초과했습니다.",
                        finished_at=now,
                    ),
                )
                state.last_job_id = timeout_job.id
                state.last_job_attempt = timeout_job.attempt
                state.last_job_status = str(AIJobStatus.FAILED)
                await self.outbox.enqueue(
                    session,
                    session_id=lecture_session.id,
                    partition_key=f"session:{lecture_session.id}",
                    event_type="clustering.updated",
                    resource_version=max(1, state.requested_sequence),
                    payload={
                        "clustering_state": QuestionService.project_clustering_state(
                            state, active=None, last=timeout_job
                        ).model_dump(mode="json")
                    },
                )

        answers = list(
            await session.scalars(
                select(Answer)
                .where(
                    Answer.session_id == lecture_session.id,
                    Answer.status == "COMPLETED",
                    Answer.source_transcript_version_id.is_not(None),
                )
                .with_for_update()
            )
        )
        for answer in answers:
            existing = await session.scalar(
                select(AIJob)
                .where(
                    AIJob.job_type == AIJobType.ANSWER_ORGANIZATION,
                    AIJob.target_answer_id == answer.id,
                )
                .with_for_update()
            )
            if existing is None:
                await self._add_timeout_job(
                    session,
                    AIJob(
                        session_id=lecture_session.id,
                        job_type=AIJobType.ANSWER_ORGANIZATION,
                        visibility=AIJobVisibility.SHARED,
                        status=AIJobStatus.FAILED,
                        attempt=1,
                        version=1,
                        target_answer_id=answer.id,
                        input_transcript_version_id=answer.source_transcript_version_id,
                        input_start_segment_id=answer.start_segment_id,
                        input_end_segment_id=answer.end_segment_id,
                        blocks_session_completion=True,
                        retryable=True,
                        error_code="SESSION_PROCESSING_TIMEOUT",
                        error_message="수업 후처리 제한 시간을 초과했습니다.",
                        finished_at=now,
                    ),
                )

    async def _add_timeout_job(self, session: AsyncSession, job: AIJob) -> AIJob:
        session.add(job)
        await session.flush()
        await self._emit_job(session, job)
        return job

    async def _first_last_segment(
        self, session: AsyncSession, version_id: UUID
    ) -> tuple[TranscriptSegment | None, TranscriptSegment | None]:
        rows = list(
            await session.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_version_id == version_id)
                .order_by(TranscriptSegment.sequence)
            )
        )
        return (rows[0], rows[-1]) if rows else (None, None)

    async def _emit_job(self, session: AsyncSession, job: AIJob) -> None:
        await self.outbox.enqueue(
            session,
            session_id=job.session_id,
            partition_key=f"session:{job.session_id}",
            event_type="job.updated",
            resource_version=job.version,
            payload=project_ai_job(job).model_dump(mode="json"),
        )

    @staticmethod
    def _is_current(job: AIJob, claimed: _ClaimedCoordinator | _ClaimedFinalAI) -> bool:
        return (
            job.status == AIJobStatus.RUNNING
            and job.attempt == claimed.attempt
            and job.run_token == claimed.run_token
        )

    @staticmethod
    def _as_run(claimed: _ClaimedCoordinator | _ClaimedFinalAI, job_type: str) -> ClaimedJob:
        return ClaimedJob(
            job_id=claimed.job_id,
            session_id=claimed.session_id,
            attempt=claimed.attempt,
            run_token=claimed.run_token,
            job_type=job_type,
        )
