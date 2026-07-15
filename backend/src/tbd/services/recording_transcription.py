"""Fenced Batch STT processing for completed Session recordings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.jobs.kernel import JobKernel
from tbd.models.enums import AIJobType, TranscriptStatus
from tbd.models.materials import (
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.providers.stt import (
    BatchSTTError,
    BatchSTTInvalidResultError,
    BatchSTTProvider,
    BatchSTTRequest,
    BatchSTTSegment,
    BatchSTTTimeoutError,
    BatchSTTUnavailableError,
    validate_batch_segments,
)
from tbd.repositories.jobs import ClaimedJob
from tbd.repositories.outbox import OutboxRepository
from tbd.repositories.recordings import RecordingRepository
from tbd.services.postprocessing import requeue_completed_coordinator
from tbd.storage import Storage, StorageError, StorageKey

HQ_STT_WORKER_LEASE = timedelta(seconds=60)
SESSION_PROCESSING_DEADLINE = timedelta(minutes=10)


def transcription_deadline(
    *, session_status: str, attempt: int, ended_at: datetime, claimed_at: datetime
) -> datetime:
    """Keep the initial Session deadline while giving explicit completed retries fresh time."""

    if session_status == "COMPLETED" and attempt > 1:
        return claimed_at + SESSION_PROCESSING_DEADLINE
    return ended_at + SESSION_PROCESSING_DEADLINE


@dataclass(frozen=True, slots=True)
class ClaimedRecordingTranscriptionWork:
    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID
    recording_id: UUID
    transcript_version_id: UUID
    storage_key: StorageKey
    content_type: str
    byte_size: int
    duration_ms: int
    deadline: datetime


class RecordingTranscriptionWorker:
    """Run one RECORDING_TRANSCRIPTION attempt without exposing recording bytes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: Storage,
        provider: BatchSTTProvider,
        *,
        repository: RecordingRepository | None = None,
        kernel: JobKernel | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.provider = provider
        self.repository = repository or RecordingRepository()
        self.kernel = kernel or JobKernel()
        self.outbox = outbox or OutboxRepository()

    async def run_once(self, *, now: datetime | None = None) -> bool:
        """Claim, transcribe, and atomically terminally record one queued attempt."""

        timestamp = now or datetime.now(UTC)
        claimed = await self._claim(timestamp)
        if claimed is None:
            return False
        if timestamp >= claimed.deadline:
            await self._finish_failure(
                claimed,
                code="HQ_STT_TIMEOUT",
                message="녹음 기반 Transcript 처리 시간이 초과되었습니다.",
                retryable=True,
                now=timestamp,
            )
            return True
        try:
            metadata = await self.storage.stat(claimed.storage_key)
            if metadata.byte_size != claimed.byte_size:
                raise StorageError("recording size changed after upload completion")
            content = await self.storage.read_range(
                claimed.storage_key, start=0, end=metadata.byte_size
            )
            segments = validate_batch_segments(
                await self.provider.transcribe(
                    BatchSTTRequest(
                        content=content,
                        content_type=claimed.content_type,
                        duration_ms=claimed.duration_ms,
                        deadline=claimed.deadline,
                    )
                ),
                duration_ms=claimed.duration_ms,
            )
        except (BatchSTTTimeoutError, TimeoutError):
            await self._finish_failure(
                claimed,
                code="HQ_STT_TIMEOUT",
                message="녹음 기반 Transcript 처리 시간이 초과되었습니다.",
                retryable=True,
                now=timestamp,
            )
        except BatchSTTUnavailableError:
            await self._finish_failure(
                claimed,
                code="HQ_STT_UNAVAILABLE",
                message="녹음 기반 Transcript 처리 서비스를 일시적으로 사용할 수 없습니다.",
                retryable=True,
                now=timestamp,
            )
        except (BatchSTTInvalidResultError, ValueError):
            await self._finish_failure(
                claimed,
                code="HQ_STT_INVALID_RESULT",
                message="녹음 기반 Transcript 결과를 처리하지 못했습니다.",
                retryable=True,
                now=timestamp,
            )
        except BatchSTTError:
            await self._finish_failure(
                claimed,
                code="HQ_STT_FAILED",
                message="녹음 기반 Transcript 처리를 완료하지 못했습니다.",
                retryable=False,
                now=timestamp,
            )
        except StorageError:
            await self._finish_failure(
                claimed,
                code="RECORDING_STORAGE_UNAVAILABLE",
                message="녹음 저장소에 일시적으로 접근할 수 없습니다.",
                retryable=True,
                now=timestamp,
            )
        else:
            await self._finish_success(claimed, segments=segments, now=timestamp)
        return True

    async def _claim(self, now: datetime) -> ClaimedRecordingTranscriptionWork | None:
        async with self.session_factory() as session:
            async with session.begin():
                candidate = await session.scalar(
                    select(AIJob)
                    .where(
                        AIJob.job_type == AIJobType.RECORDING_TRANSCRIPTION,
                        AIJob.status == "PENDING",
                        AIJob.available_at <= now,
                    )
                    .order_by(AIJob.available_at, AIJob.created_at, AIJob.id)
                    .limit(1)
                )
                if candidate is None or candidate.target_recording_id is None:
                    return None
                lecture_session = await self.repository.lock_session(session, candidate.session_id)
                if lecture_session is None or lecture_session.ended_at is None:
                    return None
                recording = await self.repository.lock_recording_for_session(
                    session, session_id=lecture_session.id
                )
                if recording is None or recording.id != candidate.target_recording_id:
                    return None
                version = await self._lock_attempt_version(
                    session,
                    session_id=lecture_session.id,
                    job_id=candidate.id,
                    attempt=candidate.attempt,
                )
                run = await self.kernel.claim_shared_by_id(
                    session,
                    candidate.id,
                    now=now,
                    lease_duration=HQ_STT_WORKER_LEASE,
                    job_type=AIJobType.RECORDING_TRANSCRIPTION,
                )
                if run is None:
                    return None
                if (
                    recording.status != "UPLOADED"
                    or recording.storage_key is None
                    or recording.content_type is None
                    or recording.byte_size is None
                    or recording.duration_ms is None
                    or version is None
                    or version.status != TranscriptStatus.FINALIZING
                ):
                    await self.kernel.cancel(session, run.job_id, now=now)
                    return None
                return ClaimedRecordingTranscriptionWork(
                    job_id=run.job_id,
                    session_id=run.session_id,
                    attempt=run.attempt,
                    run_token=run.run_token,
                    recording_id=recording.id,
                    transcript_version_id=version.id,
                    storage_key=StorageKey.parse(recording.storage_key),
                    content_type=recording.content_type,
                    byte_size=recording.byte_size,
                    duration_ms=recording.duration_ms,
                    deadline=transcription_deadline(
                        session_status=lecture_session.status,
                        attempt=run.attempt,
                        ended_at=lecture_session.ended_at,
                        claimed_at=now,
                    ),
                )

    async def _finish_success(
        self,
        claimed: ClaimedRecordingTranscriptionWork,
        *,
        segments: tuple[BatchSTTSegment, ...],
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session, recording, version = await self._lock_current(session, claimed)
                if lecture_session is None or recording is None or version is None:
                    await self.kernel.cancel(session, claimed.job_id, now=now)
                    return
                run = self._as_run(claimed)
                if not await self.kernel.succeed(session, run, now=now):
                    return
                for sequence, segment in enumerate(segments, start=1):
                    session.add(
                        TranscriptSegment(
                            session_id=claimed.session_id,
                            transcript_version_id=version.id,
                            sequence=sequence,
                            start_ms=segment.start_ms,
                            end_ms=segment.end_ms,
                            recording_start_ms=segment.recording_start_ms,
                            recording_end_ms=segment.recording_end_ms,
                            text=segment.text,
                            created_by_job_id=claimed.job_id,
                            created_by_job_attempt=claimed.attempt,
                        )
                    )
                version.last_sequence = len(segments)
                version.status = TranscriptStatus.FINALIZED if segments else TranscriptStatus.EMPTY
                version.finalized_at = now
                lecture_session.canonical_transcript_version_id = version.id
                lecture_session.version += 1
                await session.flush()
                await session.refresh(version)
                await self._emit_version_updated(session, lecture_session, version)
                await requeue_completed_coordinator(
                    session,
                    lecture_session=lecture_session,
                    now=now,
                    outbox=self.outbox,
                )

    async def _finish_failure(
        self,
        claimed: ClaimedRecordingTranscriptionWork,
        *,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session, recording, version = await self._lock_current(session, claimed)
                if lecture_session is None or recording is None or version is None:
                    await self.kernel.cancel(session, claimed.job_id, now=now)
                    return
                run = self._as_run(claimed)
                if not await self.kernel.fail(
                    session,
                    run,
                    error_code=code,
                    error_message=message,
                    retryable=retryable,
                    now=now,
                ):
                    return
                await session.execute(
                    delete(TranscriptSegment).where(
                        TranscriptSegment.transcript_version_id == version.id
                    )
                )
                await session.execute(
                    delete(TranscriptGap).where(TranscriptGap.transcript_version_id == version.id)
                )
                version.last_sequence = 0
                version.status = TranscriptStatus.FAILED
                version.failed_at = now
                await session.flush()
                await session.refresh(version)
                await self._emit_version_updated(session, lecture_session, version)

    async def _lock_current(
        self, session: AsyncSession, claimed: ClaimedRecordingTranscriptionWork
    ) -> tuple[LectureSession | None, SessionRecording | None, TranscriptVersion | None]:
        lecture_session = await self.repository.lock_session(session, claimed.session_id)
        if lecture_session is None:
            return None, None, None
        recording = await self.repository.lock_recording_for_session(
            session, session_id=claimed.session_id
        )
        version = await self._lock_attempt_version(
            session,
            session_id=claimed.session_id,
            job_id=claimed.job_id,
            attempt=claimed.attempt,
        )
        if (
            recording is None
            or recording.id != claimed.recording_id
            or version is None
            or version.id != claimed.transcript_version_id
            or version.status != TranscriptStatus.FINALIZING
        ):
            return lecture_session, None, None
        return lecture_session, recording, version

    @staticmethod
    async def _lock_attempt_version(
        session: AsyncSession, *, session_id: UUID, job_id: UUID, attempt: int
    ) -> TranscriptVersion | None:
        return await session.scalar(
            select(TranscriptVersion)
            .where(
                TranscriptVersion.session_id == session_id,
                TranscriptVersion.created_by_job_id == job_id,
                TranscriptVersion.created_by_job_attempt == attempt,
            )
            .with_for_update()
        )

    async def _emit_version_updated(
        self,
        session: AsyncSession,
        lecture_session: LectureSession,
        version: TranscriptVersion,
    ) -> None:
        canonical = None
        if lecture_session.canonical_transcript_version_id == version.id:
            canonical = version
        elif lecture_session.canonical_transcript_version_id is not None:
            canonical = await session.get(
                TranscriptVersion, lecture_session.canonical_transcript_version_id
            )
        version_payload = self._version_payload(
            version,
            is_canonical=lecture_session.canonical_transcript_version_id == version.id,
        )
        await self.outbox.enqueue(
            session,
            session_id=lecture_session.id,
            partition_key=f"session:{lecture_session.id}",
            event_type="transcript.version.updated",
            resource_version=lecture_session.version,
            payload={
                "transcript": {
                    "session_id": str(lecture_session.id),
                    "status": str(version.status),
                    "current_version": version_payload,
                    "canonical_version_id": (
                        str(lecture_session.canonical_transcript_version_id)
                        if lecture_session.canonical_transcript_version_id is not None
                        else None
                    ),
                    "canonical_version": (
                        self._version_payload(canonical, is_canonical=True)
                        if canonical is not None
                        else None
                    ),
                    "updated_at": version.updated_at.isoformat(),
                },
                "version": version_payload,
            },
        )

    @staticmethod
    def _version_payload(version: TranscriptVersion, *, is_canonical: bool) -> dict[str, object]:
        """Match the public TranscriptVersion event shape without internal storage data."""

        return {
            "id": str(version.id),
            "session_id": str(version.session_id),
            "source": str(version.source),
            "status": str(version.status),
            "version": version.version,
            "last_sequence": version.last_sequence,
            "is_canonical": is_canonical,
            "recording_id": str(version.recording_id) if version.recording_id else None,
            "created_by_job_id": (
                str(version.created_by_job_id) if version.created_by_job_id else None
            ),
            "created_by_job_attempt": version.created_by_job_attempt,
            "finalized_at": version.finalized_at.isoformat() if version.finalized_at else None,
            "failed_at": version.failed_at.isoformat() if version.failed_at else None,
            "created_at": version.created_at.isoformat(),
            "updated_at": version.updated_at.isoformat(),
        }

    @staticmethod
    def _as_run(claimed: ClaimedRecordingTranscriptionWork) -> ClaimedJob:
        return ClaimedJob(
            job_id=claimed.job_id,
            session_id=claimed.session_id,
            attempt=claimed.attempt,
            run_token=claimed.run_token,
            job_type=AIJobType.RECORDING_TRANSCRIPTION,
        )
